export async function api(path:string,body?:unknown){
 const r=await fetch(path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok){const e=await r.json().catch(()=>({detail:'Сервис временно недоступен'}));throw new Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail));}return r.json();
}
export type Message={role:string,text:string,turn_id:string};
export type Pending={operation_id:string,action:string,parameters:Record<string,unknown>,state_version:number};
export type Session={conversation_id:string,history:Message[],state_version:number,pending_action:Pending|null,response_language:'ru'|'kk'};
export const demos=[
 {name:'01 · Найти офис',detail:'Простой запрос → проверенный ответ',steps:['Где находится ваш офис в Алматы?']},
 {name:'02 · Деньги списали',detail:'Близкие ситуации → точный вопрос',steps:['Ақша списали, бірақ полис келмеді','Полис вообще не выпустился после оплаты. Мой телефон +77010000003, оплата была 30 сентября 2026 года.']},
 {name:'03 · Исправить сведения',detail:'Новые данные заменяют прежние',steps:['Хочу поменять email, ИИН 850314300121. Новый адрес first@example.com','Нет, ошибся: новый email second@example.com']},
 {name:'04 · Вернуться к теме',detail:'Прервать вопрос и продолжить его',steps:['Хочу расторгнуть полис SQ-OGPO-105120: продал машину.','Кстати, где ваш офис в Алматы?','Вернёмся к расторжению моего полиса.']},
 {name:'05 · Подтвердить действие',detail:'Предпросмотр → подтверждение',steps:['Хочу изменить email. Мой ИИН 850314300121, новый адрес demo@example.com.']},
 {name:'06 · Қазақша сөйлесейік',detail:'Қазақша сұрақ → дерекке сүйенген жауап',steps:['Алматыдағы кеңсеңіз қайда орналасқан? Қазақша жауап беріңізші.']},
];
