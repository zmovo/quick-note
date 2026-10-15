const base = location.pathname.endsWith('/') ? location.pathname : `${location.pathname}/`;
const token = base.split('/')[1];
const $ = (id) => document.getElementById(id);
const state = { days: {}, topics: [], selectedTopic: '全部分类', selectedDay: null, today: '', trend: false };
let dialogResult;
let lastSnapshot = '';

function notice(message, error = false) {
  const node = $('toast');
  node.textContent = message;
  node.className = `show${error ? ' error' : ''}`;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => { node.className = ''; }, 2800);
}

async function request(path, options) {
  const response = await fetch(`${base}api/${path}`, { cache: 'no-store', ...options });
  let data;
  try { data = await response.json(); } catch { throw new Error('无法读取本地服务响应'); }
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
}

async function action(name, details = {}) {
  await request('action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Quick-Note': token },
    body: JSON.stringify({ action: name, ...details }),
  });
  await refresh();
}

async function refresh(silent = false) {
  try {
    const data = await request('state');
    const snapshot = JSON.stringify(data);
    if (snapshot === lastSnapshot) {
      if (!silent) notice('已是最新');
      return;
    }
    lastSnapshot = snapshot;
    state.days = data.days;
    state.topics = data.topics;
    state.selectedTopic = data.selectedTopic;
    state.today = data.today;
    const dates = Object.keys(state.days);
    if (!dates.includes(state.selectedDay)) state.selectedDay = dates[0] || null;
    render();
    if (!silent) notice('已更新记录');
  } catch (error) { notice(error.message, true); }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function render() {
  const dates = Object.keys(state.days);
  $('day-count').textContent = dates.length;
  $('dates').replaceChildren(...dates.map(day => {
    const button = el('button', `date-button${day === state.selectedDay ? ' active' : ''}`);
    button.type = 'button';
    button.append(el('span', '', `${day.slice(5).replace('-', ' / ')}`), el('small', '', day === state.today ? '今天' : day.slice(0, 4)));
    button.addEventListener('click', () => { state.selectedDay = day; render(); });
    return button;
  }));
  const select = $('topic-select');
  select.replaceChildren(...['全部分类', ...state.topics].map(topic => {
    const option = el('option', '', topic);
    option.value = topic;
    return option;
  }));
  select.value = state.selectedTopic;
  $('add-entry-topic').replaceChildren(...state.topics.map(topic => {
    const option = el('option', '', topic);
    option.value = topic;
    return option;
  }));
  $('add-entry-topic').value = state.selectedTopic === '全部分类' ? '未分类' : state.selectedTopic;
  $('delete-topic').disabled = ['全部分类', '未分类'].includes(state.selectedTopic);
  $('topic-hint').textContent = state.selectedTopic === '全部分类'
    ? '显示所有分类 · 新记录归入“未分类”'
    : `筛选“${state.selectedTopic}” · 新记录归入此分类`;
  $('day-label').textContent = state.selectedDay === state.today ? '今天' : state.selectedDay ? '历史记录' : '开始记录';
  $('day-title').textContent = state.selectedDay ? state.selectedDay.replaceAll('-', ' / ') : '每日笔记';
  const groups = state.days[state.selectedDay] || { '今日学习': [], '待补齐': [] };
  const visible = category => (groups[category] || []).map((entry, index) => ({ entry, index })).filter(({ entry }) => state.selectedTopic === '全部分类' || entry[2] === state.selectedTopic);
  const review = visible('今日学习');
  const fill = visible('待补齐');
  const columns = document.querySelectorAll('.record-column');
  columns[0].hidden = false;
  columns[0].classList.toggle('is-empty', review.length === 0);
  columns[1].hidden = fill.length === 0;
  $('review-count').textContent = review.length;
  $('fill-count').textContent = fill.length;
  const count = review.length + fill.length;
  $('day-summary').textContent = count ? `共 ${count} 条记录${state.selectedTopic === '全部分类' ? '' : ` · 分类：${state.selectedTopic}`}` : '';
  const filtered = state.selectedTopic !== '全部分类';
  $('empty-state').hidden = count > 0;
  $('show-all').hidden = !filtered;
  document.querySelector('.board').hidden = count === 0;
  $('empty-title').textContent = filtered ? `这一天没有“${state.selectedTopic}”记录` : '还没有记录';
  $('empty-description').textContent = filtered
    ? '可以查看其他分类，或选中文字后按 Alt+1 / Alt+2 保存到当前分类。'
    : '在任意应用中选中文字，按 Alt+1 记入待复习，按 Alt+2 记入待补全。';
  renderCards('review-list', '今日学习', review);
  renderCards('fill-list', '待补齐', fill);
  if (state.trend) renderChart();
}

function renderCards(id, category, rows) {
  const container = $(id);
  if (!rows.length) {
    const empty = el('div', 'column-empty', '暂无记录');
    container.replaceChildren(empty);
    return;
  }
  container.replaceChildren(...rows.map(({ entry, index }) => {
    const [stamp, content, topic] = entry;
    const card = el('article', 'card');
    const top = el('div', 'card-top');
    const actions = el('div', 'card-actions');
    const day = state.selectedDay;
    const edit = iconButton('编辑记录', 'M16 3l5 5M4 16l-1 5 5-1L21 7a2 2 0 0 0-4-4Z');
    edit.type = 'button';
    edit.addEventListener('click', async () => {
      $('edit-content').value = content;
      $('edit-content').dataset.day = day;
      $('edit-content').dataset.category = category;
      $('edit-content').dataset.topic = topic;
      updateComposerPreview($('edit-content'), 'edit-image-preview');
      $('edit-error').textContent = '';
      $('edit-dialog').showModal();
      $('edit-content').focus();
      $('edit-form').onsubmit = async event => {
        event.preventDefault();
        const next = $('edit-content').value.trim();
        if (!next) { $('edit-error').textContent = '记录内容不能为空'; return; }
        $('edit-save').disabled = true;
        try {
          await action('updateEntry', { category, day, index, content: next, original: content });
          $('edit-dialog').close();
          notice('已保存修改');
        } catch (error) { $('edit-error').textContent = error.message; }
        finally { $('edit-save').disabled = false; }
      };
    });
    const remove = iconButton('删除记录', 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7', 'delete');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (await ask('删除记录', '确定删除这条记录吗？此操作无法撤销。')) await run(() => action('deleteEntry', { category, day, index }));
    });
    actions.append(edit, remove);
    const topicTag = el('select', 'tag card-topic');
    topicTag.title = '点击切换这张卡片的分类';
    topicTag.setAttribute('aria-label', '卡片分类');
    topicTag.replaceChildren(...state.topics.map(name => {
      const option = el('option', '', name);
      option.value = name;
      return option;
    }));
    topicTag.value = topic;
    topicTag.addEventListener('change', async () => {
      const next = topicTag.value;
      if (next === topic) return;
      topicTag.disabled = true;
      try {
        await action('setTopic', { category, day, index, topic: next });
        notice(`已归入“${next}”`);
      } catch (error) {
        topicTag.value = topic;
        notice(error.message, true);
      } finally { topicTag.disabled = false; }
    });
    top.append(el('span', 'time', stamp.slice(11)), topicTag, actions);
    card.append(top, renderBody(content, day));
    return card;
  }));
}

function imageSource(source, day) {
  if (/^https?:\/\//i.test(source)) return source;
  if (/^[a-z][a-z\d+.-]*:/i.test(source) || /^[\\/]/.test(source)) return null;
  const root = new URL(`${base}images/`, location.origin);
  const url = new URL(source, new URL(`${day}/`, root));
  if (!url.href.startsWith(root.href) || !/\.(png|jpe?g|gif|webp|bmp)$/i.test(url.pathname)) return null;
  return url.href;
}

function renderBody(content, day) {
  const body = el('div', 'card-body');
  // 只扩展图片语法；正文仍作为纯文字输出。
  const images = /!\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+"[^"\n]*")?\s*\)/g;
  let offset = 0;
  for (const match of content.matchAll(images)) {
    const source = imageSource(match[2] || match[3], day);
    if (!source) continue;
    body.append(document.createTextNode(content.slice(offset, match.index)));
    const figure = el('figure', 'record-image');
    const image = el('img');
    image.alt = match[1] || '记录图片';
    image.loading = 'lazy';
    image.decoding = 'async';
    image.referrerPolicy = 'no-referrer';
    const failure = el('span', 'image-failure', `图片无法加载${match[1] ? `：${match[1]}` : ''}`);
    failure.hidden = true;
    image.addEventListener('error', () => { image.hidden = true; failure.hidden = false; });
    image.src = source;
    const link = el('a', 'image-link');
    link.href = source;
    link.href = '#image-preview';
    link.title = '点击预览图片';
    link.setAttribute('aria-label', `预览图片：${image.alt}`);
    link.addEventListener('click', event => {
      event.preventDefault();
      $('image-preview-image').src = source;
      $('image-preview-image').alt = image.alt;
      $('image-preview').showModal();
    });
    link.append(image);
    figure.append(link, failure);
    body.append(figure);
    offset = match.index + match[0].length;
  }
  body.append(document.createTextNode(content.slice(offset)));
  return body;
}

function updateComposerPreview(textarea, previewId) {
  const preview = $(previewId);
  const day = textarea.dataset.day || state.today;
  const pattern = /!\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|([^\s)]+))(?:\s+"[^"\n]*")?\s*\)/g;
  const images = [...textarea.value.matchAll(pattern)].map(match => ({
    markdown: match[0], alt: match[1] || '记录图片', source: imageSource(match[2] || match[3], day),
  })).filter(image => image.source);
  if (!images.length) { preview.hidden = true; preview.replaceChildren(); return; }
  preview.hidden = false;
  preview.replaceChildren(...images.map(({ markdown, alt, source }) => {
    const item = el('div', 'composer-image-item');
    const image = el('img');
    image.src = source;
    image.alt = alt;
    image.addEventListener('click', () => {
      $('image-preview-image').src = source;
      $('image-preview-image').alt = alt;
      $('image-preview').showModal();
    });
    const remove = el('button', 'composer-image-remove', '移除图片');
    remove.type = 'button';
    remove.addEventListener('click', () => {
      const index = textarea.value.indexOf(markdown);
      if (index >= 0) textarea.setRangeText('', index, index + markdown.length, 'preserve');
      updateComposerPreview(textarea, previewId);
      textarea.focus();
    });
    item.append(image, remove);
    return item;
  }));
}

function renderChart() {
  const days = Object.keys(state.days).sort();
  if (!days.length) { $('chart').textContent = '有记录后显示趋势'; return; }
  const width = Math.max($('chart').clientWidth, days.length * 76 + 70);
  const height = 160, left = 38, right = 25, bottom = 119;
  const max = Math.max(1, ...days.flatMap(day => ['今日学习', '待补齐'].map(type => state.days[day][type].length)));
  const x = i => left + i * (width - left - right) / Math.max(1, days.length - 1);
  const y = count => bottom - count / max * 81;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', width); svg.setAttribute('height', height);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const node = (tag, attrs, content) => {
    const item = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
    if (content != null) item.textContent = content;
    svg.append(item);
  };
  node('line', { x1: left, y1: bottom, x2: width - right, y2: bottom, stroke: '#49545a' });
  [['今日学习', '#91c3a9'], ['待补齐', '#d6bb88']].forEach(([type, color]) => {
    const points = days.map((day, i) => [x(i), y(state.days[day][type].length)]);
    if (points.length > 1) node('polyline', { points: points.map(point => point.join(',')).join(' '), fill: 'none', stroke: color, 'stroke-width': 2 });
    points.forEach(([px, py], i) => {
      node('circle', { cx: px, cy: py, r: 4, fill: color, stroke: 'white', 'stroke-width': 2 });
      const count = state.days[days[i]][type].length;
      if (count) node('text', { x: px, y: py - 10, fill: color, 'font-size': 10, 'text-anchor': 'middle' }, count);
    });
  });
  days.forEach((day, i) => node('text', { x: x(i), y: 143, fill: '#a7b3ac', 'font-size': 10, 'text-anchor': 'middle' }, day.slice(5)));
  $('chart').replaceChildren(svg);
}

function ask(title, description, label = '', value = '') {
  const dialog = $('dialog');
  $('dialog-title').textContent = title;
  $('dialog-description').textContent = description;
  $('dialog-label').textContent = label;
  $('dialog-input').hidden = !label;
  $('dialog-input').value = value;
  dialog.showModal();
  if (label) $('dialog-input').focus();
  return new Promise(resolve => { dialogResult = resolve; });
}

$('dialog').addEventListener('close', () => {
  if (dialogResult) {
    dialogResult($('dialog').returnValue === 'confirm' ? ($('dialog-input').hidden ? true : $('dialog-input').value.trim()) : null);
    dialogResult = null;
  }
});

function iconButton(label, path, className = '') {
  const button = el('button', className);
  button.type = 'button';
  button.title = label;
  button.setAttribute('aria-label', label);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' })) svg.setAttribute(key, value);
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  line.setAttribute('d', path);
  svg.append(line);
  button.append(svg);
  return button;
}

$('edit-cancel').addEventListener('click', () => { if (!$('edit-save').disabled) $('edit-dialog').close(); });
$('edit-dialog').addEventListener('cancel', event => { if ($('edit-save').disabled) event.preventDefault(); });
$('image-preview-close').addEventListener('click', () => $('image-preview').close());
$('image-preview').addEventListener('click', event => {
  if (event.target === $('image-preview')) $('image-preview').close();
});

async function run(task) { try { await task(); } catch (error) { notice(error.message, true); } }

$('add-entry').addEventListener('click', () => {
  const day = state.selectedDay || state.today;
  $('add-entry-context').textContent = `${day} · ${state.selectedTopic === '全部分类' ? '未分类' : state.selectedTopic}`;
  $('add-entry-content').value = '';
  $('add-entry-content').dataset.day = day;
  $('add-entry-content').dataset.category = $('add-entry-category').value;
  $('add-entry-content').dataset.topic = $('add-entry-topic').value;
  updateComposerPreview($('add-entry-content'), 'add-entry-image-preview');
  $('add-entry-error').textContent = '';
  $('add-entry-dialog').showModal();
  $('add-entry-content').focus();
});
$('add-entry-category').addEventListener('change', () => {
  $('add-entry-content').dataset.category = $('add-entry-category').value;
});
$('add-entry-topic').addEventListener('change', () => {
  $('add-entry-content').dataset.topic = $('add-entry-topic').value;
});

for (const textarea of [$('add-entry-content'), $('edit-content')]) {
  textarea.addEventListener('paste', async event => {
    const imageItem = [...(event.clipboardData?.items || [])].find(item => item.type.startsWith('image/'));
    if (!imageItem) return;
    event.preventDefault();
    const blob = imageItem.getAsFile();
    if (!blob) { notice('无法读取剪贴板图片', true); return; }
    const extension = blob.type === 'image/png' ? '.png' : blob.type === 'image/bmp' ? '.bmp' : null;
    if (!extension) { notice('暂只支持粘贴 PNG 或 BMP 图片', true); return; }
    if (blob.size > 64 * 1024 * 1024) { notice('图片超过 64 MB，无法粘贴', true); return; }
    try {
      const metadata = {
        day: textarea.dataset.day || state.today,
        category: textarea.dataset.category || '今日学习',
        topic: textarea.dataset.topic || (state.selectedTopic === '全部分类' ? '未分类' : state.selectedTopic),
        extension,
      };
      const response = await fetch(`${base}api/paste-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream', 'X-Quick-Note': token,
          'X-Quick-Note-Image': btoa(unescape(encodeURIComponent(JSON.stringify(metadata)))) },
        body: blob,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '图片粘贴失败');
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const prefix = start > 0 && textarea.value[start - 1] !== '\n' ? '\n' : '';
      const insertion = `${prefix}${data.markdown}\n`;
      textarea.setRangeText(insertion, start, end, 'end');
      textarea.focus();
      updateComposerPreview(textarea, textarea.id === 'add-entry-content' ? 'add-entry-image-preview' : 'edit-image-preview');
      notice('图片已插入内容');
    } catch (error) { notice(error.message, true); }
  });
}
for (const textarea of [$('add-entry-content'), $('edit-content')]) {
  textarea.addEventListener('input', () => updateComposerPreview(
    textarea, textarea.id === 'add-entry-content' ? 'add-entry-image-preview' : 'edit-image-preview'));
}
$('add-entry-cancel').addEventListener('click', () => {
  if (!$('add-entry-save').disabled) $('add-entry-dialog').close();
});
$('add-entry-dialog').addEventListener('cancel', event => {
  if ($('add-entry-save').disabled) event.preventDefault();
});
$('add-entry-form').addEventListener('submit', async event => {
  event.preventDefault();
  const content = $('add-entry-content').value.trim();
  if (!content) { $('add-entry-error').textContent = '卡片内容不能为空'; return; }
  const day = state.selectedDay || state.today;
  const category = $('add-entry-category').value;
  const topic = $('add-entry-topic').value;
  $('add-entry-save').disabled = true;
  try {
    await action('addEntry', { category, day, topic, content });
    $('add-entry-dialog').close();
    state.selectedDay = day;
    notice('已添加知识卡片');
  } catch (error) { $('add-entry-error').textContent = error.message; }
  finally { $('add-entry-save').disabled = false; }
});

$('topic-select').addEventListener('change', event => run(() => action('selectTopic', { topic: event.target.value })));
$('add-topic').addEventListener('click', async () => {
  const name = await ask('新增分类', '给新的知识分类起个名字。', '分类名称');
  if (name) await run(async () => { await action('addTopic', { topic: name }); await action('selectTopic', { topic: name }); });
});
$('delete-topic').addEventListener('click', async () => {
  const name = state.selectedTopic;
  if (!['全部分类', '未分类'].includes(name) && await ask('删除分类', `删除“${name}”？已有记录会归入“未分类”。`)) await run(() => action('deleteTopic', { topic: name }));
});
$('refresh').addEventListener('click', () => refresh());
$('show-all').addEventListener('click', () => run(() => action('selectTopic', { topic: '全部分类' })));
$('trend-toggle').addEventListener('click', () => {
  state.trend = !state.trend;
  $('trend').hidden = !state.trend;
  $('trend-toggle').setAttribute('aria-expanded', String(state.trend));
  $('trend-toggle').querySelector('span').textContent = state.trend ? '收起趋势' : '查看趋势';
  if (state.trend) renderChart();
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true); });
setInterval(() => { if (!document.hidden) refresh(true); }, 1500);
refresh(true);
