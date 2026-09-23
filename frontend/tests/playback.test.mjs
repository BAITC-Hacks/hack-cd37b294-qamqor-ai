import {test} from 'node:test';
import assert from 'node:assert/strict';
import {PlaybackGate} from '../lib/playback.mjs';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
function browser(t,{supported=true,open=true,allocationFails=false,decodeFails=false}={}){
 const sources=new Map(),audios=[],buffers=[],revoked=[];
 let clock=100;
 t.mock.method(performance,'now',()=>clock+=10);
 t.mock.method(URL,'createObjectURL',source=>{const url='blob:'+sources.size;sources.set(url,source);return url;});
 t.mock.method(URL,'revokeObjectURL',url=>revoked.push(url));
 class Buffer extends EventTarget {
  constructor(){super();this.chunks=[];this.updating=false;buffers.push(this);}
  appendBuffer(value){assert.equal(this.updating,false);this.updating=true;this.chunks.push([...value]);queueMicrotask(()=>{this.updating=false;this.dispatchEvent(new Event(decodeFails?'error':'updateend'));});}
  abort(){this.updating=false;}
 }
 class Media extends EventTarget {
  static isTypeSupported(mime){assert.equal(mime,'audio/mpeg');return supported;}
  constructor(){super();this.readyState='closed';}
  addSourceBuffer(){if(allocationFails)throw new Error('unsupported');return new Buffer();}
  endOfStream(){this.readyState='ended';}
 }
 class Audio extends EventTarget {
  constructor(src){super();this.src=src;this.started=false;this.paused=false;audios.push(this);}
  load(){const media=sources.get(this.src);if(open&&media instanceof Media&&media.readyState==='closed')queueMicrotask(()=>{media.readyState='open';media.dispatchEvent(new Event('sourceopen'));});}
  async play(){this.started=true;this.dispatchEvent(new Event('playing'));}
  pause(){this.paused=true;}
 }
 for(const [name,value] of [['MediaSource',Media],['Audio',Audio]]){
  const original=Object.getOwnPropertyDescriptor(globalThis,name);
  Object.defineProperty(globalThis,name,{configurable:true,writable:true,value});
  t.after(()=>{if(original)Object.defineProperty(globalThis,name,original);else delete globalThis[name];});
 }
 return {audios,buffers,sources,revoked};
}
function audioResponse(){
 let controller,cancelled=false;
 const body=new ReadableStream({start(value){controller=value;},cancel(){cancelled=true;}});
 return {response:new Response(body,{headers:{'content-type':'audio/mpeg'}}),controller,get cancelled(){return cancelled;}};
}

test('barge-in stops audio and rejects a late TTS result',async()=>{
 const p=new PlaybackGate();let stopped=false;p.audio={pause(){stopped=true},src:'old'};
 const old=p.generation,signal=p.signal(old);p.interrupt();
 assert.equal(stopped,true);assert.equal(signal.aborted,true);assert.equal(p.current(old),false);
 assert.equal(await p.play(new Blob(),old),false);assert.equal(p.current(p.generation),true);
 assert.equal(p.signal(old).aborted,true);assert.equal(p.signal(p.generation).aborted,false);
});
test('MP3 starts before EOF and reports first byte, playing and completion separately',async t=>{
 const fake=browser(t),stream=audioResponse(),gate=new PlaybackGate(),events=[];
 const result=gate.playResponse(stream.response,0,value=>events.push(value),{responseReadyAt:50});
 stream.controller.enqueue(new Uint8Array([1,2,3]));await tick();
 assert.equal(fake.audios[0].started,true);assert.deepEqual(fake.buffers[0].chunks,[[1,2,3]]);
 assert.equal(events.at(-1).streaming,true);assert.ok(events.at(-1).first_playback_ms>events[0].response_ready_to_first_byte_ms);
 assert.equal(events.at(-1).complete_stream_ms,null);
 stream.controller.enqueue(new Uint8Array([4,5]));stream.controller.close();
 assert.equal(await result,true);assert.deepEqual(fake.buffers[0].chunks,[[1,2,3],[4,5]]);
 assert.ok(events.at(-1).complete_stream_ms>events.at(-1).first_playback_ms);
 fake.audios[0].dispatchEvent(new Event('ended'));assert.equal(gate.audio,null);assert.equal(fake.revoked.length,1);
});
test('barge-in aborts a pending stream and suppresses late playback callbacks',async t=>{
 const fake=browser(t),stream=audioResponse(),gate=new PlaybackGate(),events=[];
 const signal=gate.signal(0),result=gate.playResponse(stream.response,0,event=>events.push(event));
 stream.controller.enqueue(new Uint8Array([1]));await tick();
 const audio=fake.audios[0],count=events.length;gate.interrupt();
 assert.equal(await result,false);assert.equal(signal.aborted,true);assert.equal(stream.cancelled,true);
 assert.equal(audio.paused,true);assert.equal(audio.src,'');assert.equal(gate.mediaSource,null);
 audio.dispatchEvent(new Event('playing'));assert.equal(events.length,count);
 assert.equal(events.at(-1).complete_stream_ms,null);
});
test('barge-in cancels while MediaSource is still opening',async t=>{
 browser(t,{open:false});const stream=audioResponse(),gate=new PlaybackGate();
 const result=gate.playResponse(stream.response,0);await tick();gate.interrupt();
 assert.equal(await result,false);assert.equal(gate.audio,null);
});
test('unsupported browsers buffer the full file and preserve first-byte timing',async t=>{
 const fake=browser(t,{supported:false}),stream=audioResponse(),gate=new PlaybackGate(),events=[];
 const result=gate.playResponse(stream.response,0,event=>events.push(event));
 stream.controller.enqueue(new Uint8Array([1,2]));await tick();
 assert.equal(fake.audios.length,0);assert.ok(events[0].response_ready_to_first_byte_ms>=0);assert.equal(events[0].first_playback_ms,null);
 stream.controller.enqueue(new Uint8Array([3,4]));stream.controller.close();assert.equal(await result,true);
 assert.equal(fake.audios.length,1);assert.equal([...fake.sources.values()][0].size,4);
 assert.equal(events.at(-1).streaming,false);assert.ok(events.at(-1).first_playback_ms>=events.at(-1).complete_stream_ms);
});
test('SourceBuffer allocation failure falls back before playback',async t=>{
 const fake=browser(t,{allocationFails:true}),stream=audioResponse(),gate=new PlaybackGate(),events=[];
 stream.controller.enqueue(new Uint8Array([1]));stream.controller.close();
 assert.equal(await gate.playResponse(stream.response,0,event=>events.push(event)),true);
 assert.equal(fake.audios[0].started,false);assert.equal(fake.audios[0].paused,true);
 assert.equal(fake.audios[1].started,true);assert.equal(events.at(-1).streaming,false);
});
test('decoder failure aborts network and leaves no stale audio',async t=>{
 const fake=browser(t,{decodeFails:true}),stream=audioResponse(),gate=new PlaybackGate(),signal=gate.signal(0);
 stream.controller.enqueue(new Uint8Array([1]));
 await assert.rejects(gate.playResponse(stream.response,0),/decoding/);
 assert.equal(signal.aborted,true);assert.equal(stream.cancelled,true);assert.equal(gate.audio,null);assert.equal(fake.audios[0].started,false);
});
test('empty audio is an error, not a successful playback measurement',async t=>{
 browser(t,{supported:false});const stream=audioResponse(),gate=new PlaybackGate(),events=[];stream.controller.close();
 await assert.rejects(gate.playResponse(stream.response,0,event=>events.push(event)),/no audio/);assert.deepEqual(events,[]);
});
test('old responses are cancelled without playback and legacy blob playback still works',async t=>{
 const fake=browser(t),stream=audioResponse(),gate=new PlaybackGate();gate.interrupt();
 assert.equal(await gate.playResponse(stream.response,0),false);assert.equal(stream.cancelled,true);assert.equal(fake.audios.length,0);
 assert.equal(await gate.play(new Blob(['mp3']),1),true);assert.equal(fake.audios[0].started,true);
});
