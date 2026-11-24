import {element, pretty} from './client.js';

const labels = {
  READY:'通过', MISMATCH:'差异待复核', OFFSET_LIMIT:'误差超限', OUTSIDE_SYNC:'同步覆盖外',
  SYNC_ORDER:'同步点异常', EXPECTED_ONE_READING:'读数不唯一', EXPECTED_ONE_CHECK:'检查点不唯一',
  PENDING:'待复核', APPROVED:'已签发', HELD:'已暂缓',
  DEVICE_DRIFT:'设备漂移', BASELINE_JUMP:'基准跳变', INSUFFICIENT_EVIDENCE:'证据不足',
};
const headers = ['业务分组', '输入行', '计算值', '参考值', '判定'];
const causes = {DEVICE_DRIFT:'漂移', BASELINE_JUMP:'跳变', INSUFFICIENT_EVIDENCE:'待定'};

export function badge(status) {
  return element('span', labels[status] || status, {class:'badge', 'data-result':status, title: status});
}

export function snapshot(report, selected, stage) {
  const stats = report.intake;
  document.querySelector('[data-metric="input"]').textContent = stats.input;
  document.querySelector('[data-metric="accepted"]').textContent = stats.accepted;
  document.querySelector('[data-metric="isolated"]').textContent = stats.rejected;
  document.querySelector('[data-metric="cases"]').textContent = report.cases?.length ?? '—';
  const table = document.querySelector('#rows');
  table.replaceChildren();
  const head = element('tr');
  const body = table.createTBody();
  if (stage === 'intake') {
    head.append(...['源行', '记录键', '业务分组', '原因码'].map(title => element('th', title, {scope:'col'})));
    for (const item of stats.isolation) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    if (!stats.isolation.length) body.insertRow().insertCell().textContent = '当前文件没有隔离行';
  } else {
    const diagnosing = stage === 'diagnose' || stage === 'balance';
    head.append(...(diagnosing ? [...headers, '归因'] : headers).map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      [row.records.length, row.measure?.value ?? '—', row.measure?.expected ?? '—'].forEach(value=>tr.insertCell().textContent=value);
      tr.insertCell().append(badge(row.status));
      if (diagnosing) {
        const cell = tr.insertCell();
        if (row.diagnosis) cell.append(badge(row.diagnosis.cause));
        else cell.textContent = '—';
      }
    }
  }
  table.createTHead().append(head);
  const picked = report.cases?.find(row=>row.case===selected);
  document.querySelector('#detail-title').textContent = picked ? `分组 ${picked.case}` : '采信摘要';
  const shown = picked ? picked.diagnosis ?? picked.measure?.evidence ?? picked.prep?.details ?? {原因:picked.status} : stats.reasons;
  document.querySelector('#detail').textContent = pretty(shown);
  let counts = report.balance ? `行数 ${report.balance.accounted}/${report.balance.input} · ${report.balance.ready} 组通过` : `采信 ${stats.accepted} 行 · 隔离 ${stats.rejected} 行`;
  if (report.balance?.anomalies) {
    const parts = Object.entries(report.balance.causes).map(([key,count])=>`${causes[key]||key} ${count}`).join(' · ');
    counts += ` · 异常 ${report.balance.diagnosed}/${report.balance.anomalies} 组已归因：${parts}`;
  }
  document.querySelector('#counts').textContent = counts;
}

export function history(items, active) {
  const target = document.querySelector('#history');
  target.replaceChildren();
  for (const run of items) {
    const button = element('button', run.id.slice(0,10), {'data-run':run.id,'aria-pressed':String(run.id===active),type:'button'});
    const item = element('li');
    item.append(button, badge(run.status));
    target.append(item);
  }
  if (!items.length) target.append(element('li','尚无执行批次'));
}
