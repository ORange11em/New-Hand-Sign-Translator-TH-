import fs from 'node:fs';
const root = 'C:/Users/Ult_Orange/Desktop/handvox/qa/chapter5_work/';
const fromStdin=process.argv.includes('--stdin');
const blocks = fromStdin ? JSON.parse(fs.readFileSync(0,'utf8')) : fs.readFileSync(root + 'chapter5_content.txt', 'utf8').trim().split(/\r?\n\s*\r?\n/);
const seg = new Intl.Segmenter('th', {granularity:'word'});
const compounds = ['โครงงาน','ภาษามือ','รู้จำ','แบบจำลอง','เว็บแคม','คำศัพท์','จุดสำคัญ','เวลาจริง','เรียลไทม์','มิลลิวินาที','ออฟไลน์','ออนไลน์','แอปพลิเคชัน','คอนโวลูชัน','ผู้ทำท่า','ท่าทาง','เมทริกซ์','คุณภาพ','ร้อยละ','ประสิทธิผล','เบื้องต้น','เพิ่มเติม','ซับซ้อน'];
function thai(t) {
  let s=[...seg.segment(t)].map((x,i,a)=>x.segment+((i<a.length-1 && /[\u0e00-\u0e7f]$/.test(x.segment) && /^[\u0e00-\u0e7f]/.test(a[i+1].segment))?'\u200b':'')).join('');
  for (const word of compounds) s=s.replace(new RegExp([...word].join('\u200b?'),'g'),word);
  return s;
}
if(fromStdin)process.stdout.write(JSON.stringify(blocks.map(thai)));
else fs.writeFileSync(root+'segmented.json',JSON.stringify(blocks.map(thai),null,2),'utf8');
