// Development-only replay probe. Reads existing committed turns, never /api/chat.
import {readFile,mkdir,writeFile,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';

const frontend=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const results=path.resolve(process.argv[2]||path.join(frontend,'../evaluation/voice-probe/results.json'));
const examples=JSON.parse(await readFile(results,'utf8')).map(row=>({language:row.language,conversation_id:row.chat.conversation_id,turn_id:row.chat.turn_id,text:row.chat.text}));
const output=path.join(frontend,'public/voice_samples');
await mkdir(output,{recursive:true});
await copyFile(path.join(frontend,'lib/playback.mjs'),path.join(output,'playback.mjs'));
const data=JSON.stringify(examples).replace(/</g,'\\u003c');
const html=`<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CallAI — проверка потокового воспроизведения</title>
<style>body{font:16px system-ui;background:#f3f6f5;color:#173a32;max-width:950px;margin:45px auto;padding:20px}h1{font-size:30px}section{background:white;padding:24px;border-radius:16px;margin:20px 0}button{background:#087f5b;color:white;border:0;padding:12px 20px;border-radius:9px;font:inherit;cursor:pointer;margin:4px}button.stop{background:#9b3636}label{display:block;margin:14px 0}input{width:95%;padding:9px;border:1px solid #bdccc7;border-radius:6px}small{color:#5c726a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f5;padding:16px}a{color:#087f5b}</style>
<h1>Потоковое воспроизведение</h1><p>Разработческая проверка готовых ответов RU / KK. Маршрутизатор и бизнес-действия не вызываются.</p>
<a href="./index.html">← Сравнение голосов</a>
<section><div id="presets"></div><label>Conversation ID<input id="session"></label><label>Turn ID<input id="turn"></label><p id="answer"></p>
<button id="play">Озвучить готовый ответ</button><button id="stop" class="stop">Прервать звук и загрузку</button>
<p id="status" role="status">Готов к проверке</p><small>Точка отсчёта — нажатие кнопки для уже готового ответа. First playback — событие браузера playing, а не измерение физического звука из динамика. Нажмите «Прервать» во время загрузки или речи для проверки barge-in.</small></section>
<section><h2>Фактические измерения, мс</h2><pre id="metrics">Ещё не измерено</pre><p id="transport"></p></section>
<script type="module">
import {PlaybackGate} from './playback.mjs';
const examples=${data};
const byId=id=>document.getElementById(id),gate=new PlaybackGate();let current=null;
function select(example){byId('session').value=example.conversation_id;byId('turn').value=example.turn_id;byId('answer').textContent=example.text;}
for(const example of examples){const button=document.createElement('button');button.textContent=example.language.toUpperCase();button.onclick=()=>select(example);byId('presets').append(button);}
if(examples.length)select(examples[0]);
byId('transport').textContent=globalThis.MediaSource?.isTypeSupported('audio/mpeg')?'Браузер поддерживает MP3 MediaSource: ожидается потоковое воспроизведение.':'MP3 MediaSource недоступен: будет использовано воспроизведение полного файла.';
byId('stop').onclick=()=>{gate.interrupt();byId('status').textContent='Прервано: звук остановлен, запрос отменён. Состояние разговора сохранено.';if(current)fetch('/api/voice/interruption',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(current)}).catch(()=>{});};
byId('play').onclick=async()=>{
 gate.interrupt();const token=gate.generation;current={conversation_id:byId('session').value.trim(),turn_id:byId('turn').value.trim()};const turn={...current};
 const responseReadyAt=performance.now();byId('status').textContent='Получаем поток TTS…';byId('metrics').textContent='Ожидание первого байта…';
 try{
  const response=await fetch('/api/voice/speech?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(turn),signal:gate.signal(token)});
  if(!response.ok)throw new Error('TTS HTTP '+response.status+': '+await response.text());
  await gate.playResponse(response,token,metrics=>{
   byId('metrics').textContent=JSON.stringify(metrics,null,2);
   fetch('/api/voice/playback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...turn,...metrics})}).catch(()=>{});
  },{responseReadyAt,onPlaying:()=>byId('status').textContent='Браузер воспроизводит речь',onEnded:()=>byId('status').textContent='Воспроизведение завершено'});
 }catch(error){if(gate.current(token))byId('status').textContent=String(error);}
};
window.addEventListener('pagehide',()=>gate.interrupt());
</script></html>`;
await writeFile(path.join(output,'playback-check.html'),html,'utf8');
console.log(`Playback probe generated for ${examples.length} committed turns at ${output}`);
