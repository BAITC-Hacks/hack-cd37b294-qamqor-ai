// A token belongs to one audible answer. Interruption never mutates chat state.
const aborted = () => new DOMException('Speech interrupted', 'AbortError');

export class PlaybackGate {
 constructor(){
  this.generation=0;this.audio=null;this.url=null;this.mediaSource=null;
  this.sourceBuffer=null;this.controller=null;this.reader=null;
 }
 current(token){return token===this.generation;}
 signal(token){
  if(!this.current(token)){const stale=new AbortController();stale.abort();return stale.signal;}
  if(!this.controller)this.controller=new AbortController();
  return this.controller.signal;
 }
 releaseAudio(){
  if(this.audio){this.audio.pause();this.audio.src='';this.audio.load?.();this.audio=null;}
  if(this.sourceBuffer&&this.mediaSource?.readyState==='open'){
   try{if(this.sourceBuffer.updating)this.sourceBuffer.abort();this.mediaSource.endOfStream();}catch{}
  }
  this.sourceBuffer=null;this.mediaSource=null;
  if(this.url){URL.revokeObjectURL(this.url);this.url=null;}
 }
 interrupt(){
  this.generation++;
  this.controller?.abort();this.controller=null;
  if(this.reader){this.reader.cancel().catch(()=>{});this.reader=null;}
  this.releaseAudio();
  return this.generation;
 }
 // Race media waits against barge-in even when a browser never resolves play().
 async wait(promise,token){
  const signal=this.signal(token);
  if(signal.aborted)throw aborted();
  let cancel;
  const stopped=new Promise((_,reject)=>{cancel=()=>reject(aborted());signal.addEventListener('abort',cancel,{once:true});});
  try{return await Promise.race([promise,stopped]);}
  finally{signal.removeEventListener('abort',cancel);}
 }
 async event(target,name,token,start){
  const signal=this.signal(token);
  if(signal.aborted)throw aborted();
  return new Promise((resolve,reject)=>{
   const cleanup=()=>{target.removeEventListener(name,done);target.removeEventListener('error',fail);signal.removeEventListener('abort',stop);};
   const done=()=>{cleanup();resolve();};
   const fail=()=>{cleanup();reject(new Error('Audio decoding failed'));};
   const stop=()=>{cleanup();reject(aborted());};
   target.addEventListener(name,done,{once:true});target.addEventListener('error',fail,{once:true});signal.addEventListener('abort',stop,{once:true});
   try{start?.();}catch(error){cleanup();reject(error);}
  });
 }
 createAudio(source,token,onPlaying,onEnded){
  this.url=URL.createObjectURL(source);this.audio=new Audio(this.url);
  const audio=this.audio;
  audio.addEventListener('playing',()=>{if(this.current(token)&&this.audio===audio)onPlaying?.();},{once:true});
  audio.addEventListener('ended',()=>{if(this.current(token)&&this.audio===audio){onEnded?.();this.releaseAudio();}},{once:true});
  return audio;
 }
 // Backward-compatible complete-file playback for existing callers.
 async play(blob,token){
  if(!this.current(token))return false;
  this.releaseAudio();
  try{await this.wait(this.createAudio(blob,token).play(),token);return this.current(token);}
  catch(error){if(!this.current(token))return false;this.releaseAudio();throw error;}
 }
 /**
  * Consume a streamed MP3 response without waiting for the complete file.
  * Metrics are partial snapshots measured from responseReadyAt. `playing` is
  * browser playback readiness, not a physical measurement at the speaker.
  * Unsupported MP3 MediaSource implementations buffer and use the same Audio API.
  */
 async playResponse(response,token,onMetrics,options={}){
  if(!this.current(token)){await response.body?.cancel();return false;}
  this.releaseAudio();
  const ready=options.responseReadyAt??performance.now();
  const elapsed=()=>Math.max(0,performance.now()-ready);
  const metrics={response_ready_to_first_byte_ms:null,first_playback_ms:null,complete_stream_ms:null,streaming:false};
  const emit=()=>{if(this.current(token)){try{onMetrics?.({...metrics});}catch{}}};
  const playing=()=>{if(metrics.first_playback_ms===null){metrics.first_playback_ms=elapsed();emit();}options.onPlaying?.();};
  const ended=()=>options.onEnded?.();
  const mime=(response.headers.get('content-type')||'audio/mpeg').split(';')[0].trim();
  const chunks=[];
  let reader=null,audio=null,playPromise=null;
  try{
   const MediaSourceClass=globalThis.MediaSource;
   const supportsStream=Boolean(response.body&&mime==='audio/mpeg'&&MediaSourceClass?.isTypeSupported(mime));
   if(supportsStream){
    this.mediaSource=new MediaSourceClass();
    const media=this.mediaSource;
    audio=this.createAudio(media,token,playing,ended);
    await this.event(media,'sourceopen',token,()=>audio.load());
    // Some browsers advertise the MIME type but cannot allocate a SourceBuffer.
    try{this.sourceBuffer=media.addSourceBuffer(mime);metrics.streaming=true;}
    catch{this.releaseAudio();audio=null;}
   }
   if(response.body){
    reader=response.body.getReader();this.reader=reader;
    while(this.current(token)){
     const {done,value}=await this.wait(reader.read(),token);
     if(done)break;
     if(!value?.byteLength)continue;
     if(metrics.response_ready_to_first_byte_ms===null){metrics.response_ready_to_first_byte_ms=elapsed();emit();}
     if(metrics.streaming){
      const buffer=this.sourceBuffer;
      await this.event(buffer,'updateend',token,()=>buffer.appendBuffer(value));
      if(!playPromise){
       // Attach the rejection handler immediately; autoplay can fail before EOF.
       playPromise=this.wait(audio.play(),token);
       playPromise.catch(()=>{});
      }
     }else chunks.push(value);
    }
   }else{
    const blob=await this.wait(response.blob(),token);
    if(blob.size){metrics.response_ready_to_first_byte_ms=elapsed();emit();chunks.push(blob);}
   }
   if(!this.current(token))return false;
   if(metrics.response_ready_to_first_byte_ms===null)throw new Error('Speech response contained no audio');
   metrics.complete_stream_ms=elapsed();emit();
   if(metrics.streaming){this.mediaSource.endOfStream();await playPromise;}
   else{audio=this.createAudio(new Blob(chunks,{type:mime}),token,playing,ended);await this.wait(audio.play(),token);}
   return this.current(token);
  }catch(error){
   if(!this.current(token))return false;
   this.controller?.abort();this.controller=null;
   await reader?.cancel().catch(()=>{});
   this.releaseAudio();options.onEnded?.();
   throw error;
  }finally{
   if(this.reader===reader)this.reader=null;
   try{reader?.releaseLock();}catch{}
  }
 }
}
