(function () {
    'use strict';

    // ------------------------------------------------------------------ //
    // 浏览器预览用的假数据（真机上 JmNative 一定存在）
    // ------------------------------------------------------------------ //
    var USE_MOCK = !window.JmNative && location.search.indexOf('mock') >= 0;
    if (USE_MOCK) {
        window.JmNative = {
            snapshot: function () {
                return JSON.stringify({
                    running: true, total: 4, done: 1,
                    settings: {
                        threadsImage: 8, threadsPhoto: 4, retries: 5, proxy: '', cookie: '',
                        keepImages: false, keepZip: false, skipCrawled: false, autoResume: true,
                        pdfQuality: 90, pdfMaxWidth: 0, filenameTemplate: 'JM{id} {title}'
                    },
                    storage: '/storage/emulated/0/Android/data/com.jmcomic.app/files',
                    tasks: [
                        { id: '54747', title: '【CE家族社】(C88) [りとる☆はむれっと] 古明地さとりの…', status: '完成', progress: 1, pages: 35, detail: '35 页' },
                        { id: '28650', title: '体育用具储藏室', status: '下载中', progress: 0.42, pages: 0, detail: '15/35 页' },
                        { id: '142176', title: '', status: '等待', progress: 0, pages: 0, detail: '' },
                        { id: '540931', title: '', status: '等待', progress: 0, pages: 0, detail: '' }
                    ]
                });
            },
            preview: function () { return JSON.stringify(['54747', '28650', '142176', '540931']); },
            submit: function () { return JSON.stringify({ added: 0, duplicate: 0, error: '预览模式' }); },
            stop: function () { }, clearTasks: function () { },
            saveSettings: function (j) { return j; },
            history: function () {
                return JSON.stringify([
                    { jm_id: '54747', title: '【CE家族社】(C88) 古明地さとりのエレベーター', pages: 35, time: '2026-10-28 00:12:03', name: 'JM54747.pdf' },
                    { jm_id: '1233916', title: '古明地さとりのクラスメイトと保健體育', pages: 137, time: '2026-10-27 23:41:20', name: 'JM1233916.pdf' }
                ]);
            },
            removeHistory: function () { }, clearHistory: function () { },
            openPdf: function () { }, toast: function () { },
            storagePath: function () { return '/storage/emulated/0/Android/data/com.jmcomic.app/files'; }
        };
    }

    var native = window.JmNative || null;

    // ------------------------------------------------------------------ //
    // 状态
    // ------------------------------------------------------------------ //
    var state = { running: false, total: 0, done: 0, tasks: [], settings: {}, storage: '' };
    var nodes = new Map();
    var historyCache = [];
    var parseTimer = null;
    var activePage = 'crawl';

    var ACTIVE = ['等待', '准备', '解析', '下载中', '打包 ZIP', '生成 PDF'];

    function $(sel) { return document.querySelector(sel); }

    function call(name, arg) {
        if (!native || typeof native[name] !== 'function') return null;
        try {
            return arg === undefined ? native[name]() : native[name](arg);
        } catch (e) {
            console.error(e);
            return null;
        }
    }

    function parse(json) {
        try { return JSON.parse(json); } catch (e) { return null; }
    }

    // ------------------------------------------------------------------ //
    // 提示
    // ------------------------------------------------------------------ //
    var toastTimer = null;

    function toast(message) {
        if (!message) return;
        var el = document.getElementById('toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'toast';
            el.style.cssText = 'position:fixed;left:50%;bottom:calc(78px + env(safe-area-inset-bottom));'
                + 'transform:translateX(-50%) translateY(8px);background:rgba(34,40,53,.96);color:#e9ecf3;'
                + 'border:1px solid #3b4457;border-radius:20px;padding:8px 16px;font-size:12px;z-index:50;'
                + 'opacity:0;transition:opacity .18s,transform .18s;pointer-events:none;max-width:80vw;text-align:center;';
            document.body.appendChild(el);
        }
        el.textContent = message;
        requestAnimationFrame(function () {
            el.style.opacity = '1';
            el.style.transform = 'translateX(-50%) translateY(0)';
        });
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            el.style.opacity = '0';
            el.style.transform = 'translateX(-50%) translateY(8px)';
        }, 1800);
    }

    // ------------------------------------------------------------------ //
    // 渲染：任务
    // ------------------------------------------------------------------ //
    function statusClass(status) {
        if (status === '完成') return 'ok';
        if (status === '失败') return 'err';
        if (status === '已取消') return 'cancel';
        if (status === '等待' || status === '跳过') return 'wait';
        return 'run';
    }

    function createTaskNode(task) {
        var root = document.createElement('div');
        root.className = 'task';
        root.innerHTML = '<div class="task-top">'
            + '<span class="task-id"></span><span class="pill"></span></div>'
            + '<div class="task-title"></div>'
            + '<div class="task-bottom"><div class="bar small"><i></i></div>'
            + '<span class="task-detail"></span></div>';
        root.addEventListener('click', function () {
            var current = findTask(task.id);
            if (current && current.status === '完成') {
                call('openPdf', current.id);
            }
        });
        return {
            root: root,
            id: root.querySelector('.task-id'),
            pill: root.querySelector('.pill'),
            title: root.querySelector('.task-title'),
            bar: root.querySelector('.bar i'),
            detail: root.querySelector('.task-detail')
        };
    }

    function findTask(id) {
        for (var i = 0; i < state.tasks.length; i++) {
            if (state.tasks[i].id === id) return state.tasks[i];
        }
        return null;
    }

    function updateTaskNode(node, task) {
        node.id.textContent = 'JM' + task.id;
        node.pill.textContent = task.status;
        node.pill.className = 'pill ' + statusClass(task.status);
        node.title.textContent = task.title || '等待获取标题…';
        var progress = Math.max(0, Math.min(1, task.progress || 0));
        node.bar.style.width = (progress * 100).toFixed(0) + '%';
        node.detail.textContent = task.detail || (progress > 0 ? Math.round(progress * 100) + '%' : '');
        node.root.classList.toggle('running', ACTIVE.indexOf(task.status) >= 0);
    }

    function upsertTask(task) {
        if (!task || !task.id) return;
        var existing = findTask(task.id);
        if (existing) {
            Object.assign(existing, task);
        } else {
            state.tasks.push(task);
        }
        var node = nodes.get(task.id);
        if (!node) {
            node = createTaskNode(task);
            nodes.set(task.id, node);
            $('#taskList').appendChild(node.root);
        }
        updateTaskNode(node, findTask(task.id));
        updateEmptyState();
    }

    function renderTasks(tasks) {
        var list = $('#taskList');
        list.innerHTML = '';
        nodes.clear();
        state.tasks = tasks || [];
        for (var i = 0; i < state.tasks.length; i++) {
            var node = createTaskNode(state.tasks[i]);
            nodes.set(state.tasks[i].id, node);
            list.appendChild(node.root);
            updateTaskNode(node, state.tasks[i]);
        }
        updateEmptyState();
    }

    function updateEmptyState() {
        var list = $('#taskList');
        var empty = list.querySelector('.empty');
        if (state.tasks.length === 0) {
            if (!empty) {
                empty = document.createElement('div');
                empty.className = 'empty';
                empty.textContent = '粘贴番号后点「开始爬取」；运行中可继续追加';
                list.appendChild(empty);
            }
        } else if (empty) {
            empty.remove();
        }
    }

    // ------------------------------------------------------------------ //
    // 渲染：计数 / 按钮
    // ------------------------------------------------------------------ //
    function renderCounters() {
        var total = state.total || 0;
        var done = Math.min(state.done || 0, total);
        $('#counter').textContent = done + ' / ' + total;
        $('#overallBar').style.width = total ? (done / total * 100).toFixed(0) + '%' : '0%';

        var chip = $('#statusChip');
        chip.classList.toggle('running', !!state.running);
        chip.classList.toggle('done', !state.running && total > 0 && done === total);
        $('#statusText').textContent = state.running ? '下载中' : (total ? '就绪' : '待命');

        $('#btnStart').textContent = state.running ? '追加任务' : '开始爬取';
        $('#btnStop').classList.toggle('hidden', !state.running);
        $('#btnClearTasks').style.display = state.running ? 'none' : '';
    }

    function renderChips(ids) {
        var box = $('#chips');
        if (!ids || !ids.length) {
            box.innerHTML = '<span class="hint">尚未识别到番号</span>';
            return;
        }
        var show = ids.slice(0, 8);
        var html = show.map(function (id) { return '<span class="chip">JM' + id + '</span>'; }).join('');
        if (ids.length > show.length) {
            html += '<span class="chip more">+' + (ids.length - show.length) + '</span>';
        }
        box.innerHTML = html;
    }

    // ------------------------------------------------------------------ //
    // 渲染：设置
    // ------------------------------------------------------------------ //
    function loadSettings(s) {
        if (!s) return;
        state.settings = s;
        $('#sThreadsImage').value = s.threadsImage;
        $('#sRetries').value = s.retries;
        $('#sProxy').value = s.proxy || '';
        $('#sCookie').value = s.cookie || '';
        $('#sPdfQuality').value = s.pdfQuality;
        $('#sPdfMaxWidth').value = s.pdfMaxWidth;
        $('#sTemplate').value = s.filenameTemplate;
        $('#sKeepImages').checked = !!s.keepImages;
        $('#sKeepZip').checked = !!s.keepZip;
        $('#sSkipCrawled').checked = !!s.skipCrawled;
        $('#sAutoResume').checked = !!s.autoResume;
    }

    function collectSettings() {
        return {
            threadsImage: parseInt($('#sThreadsImage').value, 10) || 16,
            threadsPhoto: 4,
            retries: parseInt($('#sRetries').value, 10) || 0,
            proxy: $('#sProxy').value.trim(),
            cookie: $('#sCookie').value.trim(),
            pdfQuality: parseInt($('#sPdfQuality').value, 10) || 90,
            pdfMaxWidth: parseInt($('#sPdfMaxWidth').value, 10) || 0,
            filenameTemplate: $('#sTemplate').value.trim() || 'JM{id} {title}',
            keepImages: $('#sKeepImages').checked,
            keepZip: $('#sKeepZip').checked,
            skipCrawled: $('#sSkipCrawled').checked,
            autoResume: $('#sAutoResume').checked
        };
    }

    // ------------------------------------------------------------------ //
    // 渲染：记录
    // ------------------------------------------------------------------ //
    function openHistory() {
        var raw = call('history');
        historyCache = parse(raw) || [];
        renderHistory();
    }

    function renderHistory() {
        var keyword = ($('#histSearch').value || '').trim().toLowerCase();
        var list = $('#histList');
        var items = historyCache.filter(function (item) {
            if (!keyword) return true;
            return String(item.jm_id || '').toLowerCase().indexOf(keyword) >= 0
                || String(item.title || '').toLowerCase().indexOf(keyword) >= 0;
        });
        $('#histCount').textContent = keyword
            ? items.length + ' / ' + historyCache.length
            : '共 ' + historyCache.length + ' 条';

        if (!items.length) {
            list.innerHTML = '<div class="empty">' + (keyword ? '没有匹配的记录' : '还没有爬取记录') + '</div>';
            return;
        }
        list.innerHTML = items.map(function (item) {
            var title = escapeHtml(item.title || '（无标题）');
            var meta = escapeHtml((item.time || '') + (item.name ? ' · ' + item.name : ''));
            return '<div class="hist" data-id="' + item.jm_id + '">'
                + '<div class="hist-top"><span class="task-id">JM' + item.jm_id + '</span>'
                + '<span class="pill ok">' + (item.pages || 0) + ' 页</span></div>'
                + '<div class="hist-title">' + title + '</div>'
                + '<div class="hist-meta">' + meta + '</div>'
                + '<div class="hist-actions">'
                + '<button class="btn primary" data-act="open">打开 PDF</button>'
                + '<button class="btn" data-act="again">重新爬取</button>'
                + '<button class="btn ghost" data-act="del">删除</button>'
                + '</div></div>';
        }).join('');
    }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ------------------------------------------------------------------ //
    // 渲染：日志
    // ------------------------------------------------------------------ //
    function addLog(level, message) {
        if (!message) return;
        var box = $('#log');
        var line = document.createElement('div');
        line.className = 'l-' + (level || 'info');
        var time = new Date().toTimeString().slice(0, 8);
        line.textContent = '[' + time + '] ' + message;
        box.appendChild(line);
        while (box.childElementCount > 400) box.removeChild(box.firstChild);
        box.scrollTop = box.scrollHeight;
        $('#logCount').textContent = ' · ' + box.childElementCount;
    }

    // ------------------------------------------------------------------ //
    // 页面切换
    // ------------------------------------------------------------------ //
    function showPage(page) {
        activePage = page;
        var pages = document.querySelectorAll('.page');
        for (var i = 0; i < pages.length; i++) {
            pages[i].classList.toggle('active', pages[i].id === 'page-' + page);
        }
        var tabs = document.querySelectorAll('.tab');
        for (var j = 0; j < tabs.length; j++) {
            tabs[j].classList.toggle('active', tabs[j].getAttribute('data-page') === page);
        }
        window.scrollTo(0, 0);
        if (page === 'history') openHistory();
    }

    // ------------------------------------------------------------------ //
    // 快照与事件
    // ------------------------------------------------------------------ //
    function applySnapshot(snapshot) {
        if (!snapshot) return;
        state.running = !!snapshot.running;
        state.total = snapshot.total || 0;
        state.done = snapshot.done || 0;
        state.storage = snapshot.storage || '';
        loadSettings(snapshot.settings);
        renderTasks(snapshot.tasks || []);
        renderCounters();
        $('#storagePath').textContent = state.storage || '—';
    }

    window.__nativeState = function (json) {
        applySnapshot(parse(json));
    };

    window.__nativeEvent = function (json) {
        var event = parse(json);
        if (!event) return;
        if (event.type === 'task') {
            upsertTask(event.task);
        } else if (event.type === 'state') {
            state.running = !!event.running;
            state.total = event.total || 0;
            state.done = event.done || 0;
            renderCounters();
            if (!state.running && activePage === 'history') openHistory();
        } else if (event.type === 'log') {
            addLog(event.level, event.msg);
        }
    };

    // ------------------------------------------------------------------ //
    // 事件绑定
    // ------------------------------------------------------------------ //
    function bind() {
        document.querySelectorAll('.tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                showPage(tab.getAttribute('data-page'));
            });
        });

        $('#input').addEventListener('input', function () {
            clearTimeout(parseTimer);
            parseTimer = setTimeout(function () {
                var ids = parse(call('preview', $('#input').value)) || [];
                renderChips(ids);
            }, 220);
        });

        $('#btnStart').addEventListener('click', function () {
            var text = $('#input').value;
            if (!text.trim()) {
                toast('请先粘贴番号');
                return;
            }
            var result = parse(call('submit', text));
            if (!result) return;
            if (result.error) {
                toast(result.error);
                return;
            }
            if (!result.added) {
                toast('这些番号已经在队列里了');
                return;
            }
            $('#input').value = '';
            renderChips([]);
            toast('已加入 ' + result.added + ' 个任务');
        });

        $('#btnStop').addEventListener('click', function () {
            call('stop');
        });

        $('#btnClearInput').addEventListener('click', function () {
            $('#input').value = '';
            renderChips([]);
        });

        $('#btnClearTasks').addEventListener('click', function () {
            if (state.running) {
                toast('正在爬取中，请先停止');
                return;
            }
            if (!state.tasks.length) return;
            if (!confirm('清空任务列表？不会删除已下载的 PDF 和记录')) return;
            call('clearTasks');
            state.tasks = [];
            state.total = 0;
            state.done = 0;
            renderTasks([]);
            renderCounters();
        });

        $('#histSearch').addEventListener('input', renderHistory);

        $('#histList').addEventListener('click', function (event) {
            var button = event.target.closest('button[data-act]');
            if (!button) return;
            var card = button.closest('.hist');
            var id = card.getAttribute('data-id');
            var action = button.getAttribute('data-act');
            if (action === 'open') {
                call('openPdf', id);
            } else if (action === 'again') {
                showPage('crawl');
                $('#input').value = 'JM' + id;
                $('#input').dispatchEvent(new Event('input'));
            } else if (action === 'del') {
                if (!confirm('删除 JM' + id + ' 的记录？不会删除 PDF')) return;
                call('removeHistory', id);
                openHistory();
            }
        });

        $('#btnClearHistory').addEventListener('click', function () {
            if (!historyCache.length) return;
            if (!confirm('清空全部爬取记录？不会删除 PDF')) return;
            call('clearHistory');
            openHistory();
        });

        $('#btnSaveSettings').addEventListener('click', function () {
            var raw = call('saveSettings', JSON.stringify(collectSettings()));
            var saved = parse(raw);
            if (saved) {
                loadSettings(saved);
                toast('设置已保存');
            } else {
                toast('保存失败');
            }
        });
    }

    // ------------------------------------------------------------------ //
    // 启动
    // ------------------------------------------------------------------ //
    function boot() {
        bind();
        var match = /[?&]page=(\w+)/.exec(location.search);
        if (match && document.getElementById('page-' + match[1])) showPage(match[1]);
        applySnapshot(parse(call('snapshot')));
        renderChips([]);
        renderCounters();
        updateEmptyState();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
