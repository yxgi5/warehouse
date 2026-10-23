# -*- coding: utf-8 -*-
"""个人物品仓库 —— 应用入口（Phase 3 重构后）

分层：
- db.py    数据层：连接/建表/迁移/备份/孤儿检测/路径解析（不依赖 streamlit）
- repo.py  访问层：items/containers/images/tags 的 CRUD 与查询（不依赖 streamlit）
- ui/      渲染层：各 Tab 的 Streamlit 渲染（sidebar/items/dashboard/timeline/tags/tree/containers；
            add 为「物品浏览」Tab 内的新增子页面，非独立 Tab）
- app.py   入口：页面配置、会话状态、Tab 调度、全局数据加载

运行:  streamlit run app.py
"""
import streamlit as st
import streamlit.components.v1 as components
import db
import repo
import i18n
from ui import sidebar, items_tab, dashboard_tab, timeline_tab, tags_tab, tree_tab, containers_tab

# --- 语言设置（set_page_config 之前；set_lang 不是 st 调用，不违反"第一个 st 调用"约束） ---
i18n.set_lang(st.session_state.get('lang', 'en'))

# --- 页面配置（必须是第一个 st 调用） ---
st.set_page_config(page_title=i18n.t("app.title"), layout="wide")

# --- 全局样式：列表工具栏固定视口底部（fixed 不依赖页面滚动） ---
# st.container(key=...) 生成 class "st-key-<key>"（Streamlit 1.39+）。
# 直接对工具栏容器本身应用 position: fixed，钉在视口底部：
# 无论页面长短、是否滚动，工具栏始终可见。left/width 用 CSS 变量
# --toolbar-left/--toolbar-width 提供（由下方 JS 随主内容区实时同步，
# 侧边栏折叠/窗口缩放时自动对齐）；fallback 21rem 对应展开侧边栏的默认宽度。
# 主内容区加足够 padding-bottom 防止 fixed 工具栏遮挡底部内容。
# 注意：必须包在带 key 的容器里（css_inject）——实测这段 markdown 的元素容器
# 本身高 41.6px + flex gap 16px，会把主区标题往下顶 57.6px（见下方 display:none）。
with st.container(key="css_inject"):
    st.markdown("""
<style>
.st-key-list_toolbar,
.st-key-container_toolbar {
    position: fixed;
    /* bottom 抬 4px：实测贴底(bottom:0)时该 fixed 容器会给 stMain 贡献 ~3px 的
       滚动溢出（主区因此常驻一根细滚动条）；抬离底边后贡献落到视口内，溢出消失 */
    bottom: 4px;
    left: var(--toolbar-left, 21rem);
    width: var(--toolbar-width, calc(100vw - 21rem));
    background: var(--toolbar-bg, #ffffff);
    /* 背景不依赖 Streamlit 主题变量：自定义 <style> 作用域内 var(--background-color)
       实测不解析、恒走回退值，浅色回退在深色主题下发白刺眼。故由下方 JS 读取
       主内容区真实背景色实时写入 --toolbar-bg（与 left/width 同机制）；JS 异常
       时最后兑底浅色。 */
    padding: 8px 0 4px;
    z-index: 1000;
    border-top: 1px solid rgba(128, 128, 128, 0.15);
    box-sizing: border-box;
}
/* Phase 10 Step1：收紧主区顶部空白。
   根因：Streamlit 在 .stMainBlockContainer 上由 styled 生成的 class 施加顶部 padding
   （wide 模式默认 2.1rem；addPaddingForHeader 时 = headerHeight+md = 4.75rem），
   普通选择器覆盖会被它压过（实测），必须 !important。外层 stAppViewContainer /
   stMain 也一并清零，避免叠加。 */
[data-testid="stAppViewContainer"] {
    padding-top: 0 !important;
}
[data-testid="stMain"] {
    padding-top: 0 !important;
    /* 46 = 吸底工具栏高(53)+bottom(4)−9px 期望间隙 + JS缓冲20 的配平值：
       提示行底边定点 = main高 − 46 − 20，距工具栏顶(main高−57)恰 9px。
       高度公式动态读 computed padding-bottom，改这里无需动 JS */
    padding-bottom: 46px !important;
}
/* header（Deploy + 菜单）实测是 <header data-testid="stHeader">（非 section，
   之前写成 section 导致整条规则从未生效）。原 position:fixed;left:0;right:0
   独占整行窗体、高 3.75rem。这里：① 收进主内容区（与吸底工具栏同宽，复用
   --toolbar-left/--toolbar-width）；② 高度压到 2.25rem(36px)——Deploy 按钮实高 32px、
   原在 header 内 top:20px，把 stToolbar 上移到 2px 后 36px 足够容纳（按钮 2..34，
   底边贴 header 底），顶部横带从 60px 进一步收窄到 36px。 */
header[data-testid="stHeader"] {
    left: var(--toolbar-left, 21rem) !important;
    width: var(--toolbar-width, calc(100vw - 21rem)) !important;
    right: auto !important;
    height: 2.25rem !important;
}
header[data-testid="stHeader"] [data-testid="stToolbar"] {
    top: 2px !important;
}
/* 主区顶部只留 header 高度(2.25rem=36px)+2px 间隙，标题紧贴 header 下方；
   padding-bottom 也要归零——实测 block 容器默认 11rem(176px) 底部内边距，
   是「列表滚到底出现大空区」的来源（吸底工具栏避让已由 stMain 的 80px 承担） */
[data-testid="stMain"] .stMainBlockContainer {
    padding-top: 2.375rem !important;
    padding-bottom: 0 !important;
}
/* 承载本段 <style> 的 markdown 元素容器实测本身高 41.6px，且作为
   stVerticalBlock 的 flex 子项还吃 16px gap——合计把标题往下顶 57.6px，
   是顶部「红框空白」的主要来源之一。<style> 在 display:none 容器内依然全局
   生效，故把整个注入容器隐藏，零成本回收这块空间。
   兜底：key 类无论落在容器包裹层还是内层都能命中（:has 覆盖外层 flex 子项）。 */
[data-testid="stMain"] .st-key-css_inject {
    display: none !important;
}
[data-testid="stMain"] [data-testid="stVerticalBlock"] > div:has(> div .st-key-css_inject) {
    display: none !important;
}
/* 工具栏按钮组作为整体在主内容区横向居中：侧边栏折叠/展开改变的是工具栏容器
   （fixed）的 left/width，按钮组中心始终保持在主内容区横向中心，不会跟着左移。
   内部列比例：物品 [2,2,2,2,5]（按钮×4 + 计数提示）、容器 [3,3,3,5]（按钮×3 +
   计数提示，新增按钮已移至浏览态控制行，Phase 10 Step1）配合 max-width 900px，
   两侧保留留白，保持整体居中的观感。
   Streamlit 的 stVerticalBlock 默认会被主题 max-width 限制，这里先让它占满 fixed 容器；
   stHorizontalBlock 再限制宽度并居中，防止按钮被压成竖排。 */
.st-key-list_toolbar [data-testid="stVerticalBlock"],
.st-key-container_toolbar [data-testid="stVerticalBlock"] {
    width: 100% !important;
    max-width: none !important;
}
.st-key-list_toolbar [data-testid="stHorizontalBlock"],
.st-key-container_toolbar [data-testid="stHorizontalBlock"] {
    width: min(900px, 100%);
    margin: 0 auto;
}
.st-key-list_toolbar button,
.st-key-container_toolbar button {
    white-space: nowrap !important;
}
/* Step 2：列表视图表格高度视口自适应。Streamlit 把高度写在内联 style 上
   （stDataFrameResizable 的 height:300px），普通选择器压不过 → !important；
   高度交给 --list-avail-h（由下方同步 JS 按视口实测写入）。卡片/详情页无此容器，
   选择器不命中即整条规则跳过；无 JS 时回退 300px（可滚动，不破功能）。 */
.st-key-item_list_wrap [data-testid="stDataFrameResizable"],
.st-key-container_list_wrap [data-testid="stDataFrameResizable"] {
    height: var(--list-avail-h, 300px) !important;
}
/* Step 2.5：选中提示行紧凑化——小字号/小内边距降占高，容器上下对称负外边距
   收紧间距（提示行所在纵排 flex gap 16px，−12 后上下各余约 4px+边框），
   底边再由 JS 定点公式压到距吸底工具栏 ~9px，整体上下等距、紧贴按钮。
   空库无提示时容器空渲染，负边距无可视影响。 */
.st-key-list_hint,
.st-key-container_hint {
    /* 上 −15 / 下 −12：flex gap 16 基础上，实测提示行上间隙 24、下 9，
       分别收紧到 9/9 对称（下间隙由 JS 定点公式压到 9） */
    margin-top: -15px !important;
    margin-bottom: -12px !important;
}
.st-key-list_hint .stAlert,
.st-key-container_hint .stAlert {
    padding: 0 !important;          /* 外壳不留白，实高在 stAlertContainer */
    font-size: 0.82rem;
}
/* 实高盒：默认 padding 16/16 + 内容行 24px = 56px 高，压到 4/4 ≈ 32px */
.st-key-list_hint [data-testid="stAlertContainer"],
.st-key-container_hint [data-testid="stAlertContainer"] {
    padding-top: 4px !important;
    padding-bottom: 4px !important;
    font-size: 0.82rem !important;
    line-height: 1.35 !important;
    min-height: 0 !important;
}
.st-key-list_hint [data-testid="stAlertContainer"] svg,
.st-key-container_hint [data-testid="stAlertContainer"] svg {
    width: 15px;
    height: 15px;
    flex-shrink: 0;
}
/* Step 3 全屏态（body.wh-list-fullscreen）：表格铺满主内容区，其余 chrome 全隐。
   隐藏项：页面标题(stHeadingWithActionElements)、Tabs 栏(stTabs)、header(Deploy)、
   浏览态控制行(items_viewrow/containers_viewrow)、选中提示。
   吸底工具栏【不隐藏】——用户反馈：全屏选中行后需要它来 查看详情/编辑/删除/导出，
   故全屏态保留并抬高 z-index 压在表格(z-index 1001)之上（工具栏底部悬浮，
   与右上角退出按钮不冲突）。
   fixed 相对 stMain（带 transform 的祖先 = 主内容矩形），故表格 top:0/height:100vh
   即铺满主内容区（与 --toolbar-left/width 同坐标系，无需感知侧边栏/header）。 */
/* 全屏态隐藏项：仅隐藏 Tab「栏」(role=tablist)——注意面板也在 stTabs 容器内，
   若整块 display:none 会把当前表格面板也灭掉（计算高度正常但 offsetHeight=0）。 */
body.wh-list-fullscreen [data-testid="stHeadingWithActionElements"],
body.wh-list-fullscreen [data-testid="stTabs"] [role="tablist"],
body.wh-list-fullscreen header[data-testid="stHeader"],
body.wh-list-fullscreen .st-key-items_viewrow,
body.wh-list-fullscreen .st-key-containers_viewrow,
body.wh-list-fullscreen .st-key-list_hint,
body.wh-list-fullscreen .st-key-container_hint {
    display: none !important;
}
/* 全屏态吸底工具栏：压到全屏表格(z-index 1001)之上，保证选中行后可操作 */
body.wh-list-fullscreen .st-key-list_toolbar,
body.wh-list-fullscreen .st-key-container_toolbar {
    z-index: 1002 !important;
}
/* 全屏态：强制 stMain 撑满视口（chrome 已隐藏，避免塌陷）；overflow 隐藏防误导滚动。 */
body.wh-list-fullscreen [data-testid="stMain"] {
    height: 100vh !important;
    overflow: hidden !important;
}
/* 表格容器：不走 fixed —— 实测 position:fixed 在带 transform 的 stMain 包含块下
   高度会塌缩（top/bottom 与 height:100vh 都撑不开，offsetHeight=0）。全屏态 chrome
   已隐藏（标题/Tabs/控制行/提示/工具栏均 display:none），故表格直接占普通流、用
   height:100vh 吃满视口；block 顶部 padding 一并清零让表格贴顶。 */
body.wh-list-fullscreen [data-testid="stMain"] .stMainBlockContainer {
    padding-top: 0 !important;
}
body.wh-list-fullscreen .st-key-item_list_wrap,
body.wh-list-fullscreen .st-key-container_list_wrap {
    /* fixed 出流铺满：普通流上方有页面级杂项占位（fs_state 容器、分隔线、
       tabpanel padding、flex gap，实测共 82px）会把表格顶下去、底部裁掉。
       fixed + height:100vh 无视全部流内杂项（fs_exit 的 fixed 已验证可行；
       此前 fixed「塌缩」实为 stTabs 整体隐藏的假象）。flex:none 解除
       Streamlit 的 flex:1 1 0（flex-basis:0 会压过 height）。 */
    position: fixed !important;
    top: 0 !important;
    left: var(--toolbar-left, 21rem) !important;
    width: var(--toolbar-width, calc(100vw - 21rem)) !important;
    flex: none !important;
    /* 100vh − 57(工具栏高53+bottom4)：全屏态工具栏保留且悬浮底部，
       表格若仍吃满 100vh，最后一行下半会被工具栏盖住 → 预留出这块高度 */
    height: calc(100vh - 57px) !important;
    margin: 0 !important;
    z-index: 1001 !important;
    background: var(--toolbar-bg, #fff);
    overflow: hidden;
}
body.wh-list-fullscreen .st-key-item_list_wrap [data-testid="stDataFrameResizable"],
body.wh-list-fullscreen .st-key-container_list_wrap [data-testid="stDataFrameResizable"] {
    flex: none !important;
    /* 用 100vh 基准而非 100%：嵌套 flex 下百分比高度解析不到父级高度，会塌成内容高；
       同步扣掉保留的吸底工具栏 57px，与外层 wrap 高度一致 */
    height: calc(100vh - 57px) !important;
    min-height: 0 !important;
}
/* 全屏态退出按钮：常驻 DOM（display:none 隐藏），仅全屏可见、置右上角 */
.st-key-fs_state { display: none !important; }   /* 仅透传变量，隐藏避免占顶部间隙 */
.st-key-fs_exit {
    position: fixed;
    top: 10px;
    right: 18px;
    z-index: 1002;
    display: none !important;
}
/* 容器及内层包装链全部收缩到内容宽：Streamlit 的块级包装会撑成 fill-available
   （实测 1402px），按钮落在容器左缘 → fixed right:18 反而显示在表格左上、
   盖住 ITEM No. 列头。全部 max-content 后容器收缩为按钮宽，贴右缘。 */
.st-key-fs_exit,
.st-key-fs_exit [data-testid],
.st-key-fs_exit > div { width: max-content !important; }
body.wh-list-fullscreen .st-key-fs_exit { display: block !important; }
.st-key-fs_exit button { white-space: nowrap !important; }
/* 照片区「添加图片/添加照片」按钮相对上传框垂直居中：原先用空行占位、按钮偏上。
   实测（selenium）：按钮列高=内容高、不随 flex 行拉伸，margin:auto 解析为 0 不居中；
   改固定下移 47.5px（= 上传框中心 − 按钮中心：按钮高 40、Dropzone 高 79.1，
   偏移由上传框上方 label 高度决定；Streamlit 升级致两者尺寸变化时需重测）。 */
.st-key-edit_photo_add_btn,
.st-key-add_photo_btn,
.st-key-container_photo_add_btn,
.st-key-container_add_photo_btn {
    margin-top: 47.5px !important;
}
</style>
""", unsafe_allow_html=True)

    # --- 工具栏定位同步（不可见 iframe）：侧边栏折叠/展开、窗口缩放时，
    # stMain 的左缘与宽度会变化，这里实时写入 CSS 变量供工具栏使用。
    # 组件 iframe 与 app 同源，可访问 parent；任何异常静默回退到 CSS fallback。
    # 与上面的 CSS 同放进 css_inject 隐藏容器：实测其元素容器即便 iframe 高 0
    # 也占 25.6px + 16px flex gap，是顶部空白的另一来源；隐藏容器的 iframe
    # 仍正常加载并执行 JS，不受 display:none 影响。---
    components.html("""
<script>
(function () {
    function sync() {
        try {
            var doc = window.parent.document;
            var main = doc.querySelector('section[data-testid="stMain"]');
            if (!main) return;
            var r = main.getBoundingClientRect();
            doc.documentElement.style.setProperty('--toolbar-left', r.left + 'px');
            doc.documentElement.style.setProperty('--toolbar-width', r.width + 'px');
            // 主区背景通常为透明（实色在 stApp 上）：沿父链取第一个非透明背景
            var bg = window.getComputedStyle(main).backgroundColor;
            var el = main;
            while (el && (!bg || bg === 'transparent' || bg === 'rgba(0, 0, 0, 0)')) {
                el = el.parentElement;
                if (!el) break;
                bg = window.getComputedStyle(el).backgroundColor;
            }
            doc.documentElement.style.setProperty('--toolbar-bg', bg || '#ffffff');
        } catch (e) { /* 跨源等异常时静默，保留 CSS fallback */ }
    }
    // Step 3 全屏态：读 :root 上的 --list-fullscreen（由 app.py 按 session_state 注入），
    // 给 parent 的 body 切 class wh-list-fullscreen，驱动全屏 CSS。不依赖 iframe 重执行
    // 时机——下方另挂 documentElement 的 style 观察者，变量一变即生效。
    function applyFullscreen() {
        try {
            var doc = window.parent.document;
            if (!doc || !doc.body) return;
            var v = getComputedStyle(doc.documentElement).getPropertyValue('--list-fullscreen').trim();
            doc.body.classList.toggle('wh-list-fullscreen', v === '1');
        } catch (e) { }
    }
    // Step 2：列表视图表格高度视口自适应。
    // 公式：可用高 = 视口高 − 表顶(视口坐标) − 选中提示 alert 高 − 主区 padding-bottom − 缓冲。
    // 吸底工具栏 position:fixed 不入流，故不计入；表格只填到 alert 之上、工具栏之下，无页面滚动条。
    // Step 2：列表视图表格高度视口自适应（v2.1 相对 main 盒模型 + 流内末底边自校正）。
    // 前两版教训（均有实测）：v1 用「视口高 − 表顶(视口坐标)」——stMain 才是真正的
    // 滚动容器(overflow:auto)，它滚动过之后表顶读数被滚动量污染，表格越算越大
    // （用户环境滚动条/大空区/提示行被顶走的根源）；v2 用 scrollingElement.scrollHeight
    // 自校正——但根元素 scrollHeight 恒等于视口高（溢出发生在 stMain 内部），slack
    // 恒为 0 导致表格一路收缩到下限，方向错误。
    // v2.1：所有量都取相对 main 盒模型的差值（滚动量在差值中自动抵消，滚过也能安全重算）：
    //   新表高 = 当前表高 + (main高 − paddingBottom − 缓冲 − 流内末元素底边)
    // 流内末元素底边 = 表格/提示 alert 中更靠下者，自动涵盖表与 alert 间的 margin、
    // 模型外的额外占位。数学上一步收敛且稳定（收敛后末底边恰在目标线上，增量归零）。
    function calcListHeight() {
        try {
            var doc = window.parent.document;
            // 注意：Streamlit 非激活 Tab 的面板仍留在 DOM（display 隐藏），querySelector
            // 按文档序会先命中隐藏的物品 wrap（高 0）→ 必须挑当前可见的那个
            var wraps = doc.querySelectorAll('.st-key-item_list_wrap, .st-key-container_list_wrap');
            var wrap = null;
            for (var i = 0; i < wraps.length; i++) {
                if (wraps[i].getBoundingClientRect().height > 0) { wrap = wraps[i]; break; }
            }
            if (!wrap) return;                       // 卡片/详情页/切换过渡中，整条跳过
            var res = wrap.querySelector('[data-testid="stDataFrameResizable"]');
            if (!res) return;
            var main = doc.querySelector('[data-testid="stMain"]');
            if (!main) return;
            var mainRect = main.getBoundingClientRect();
            var resRect = res.getBoundingClientRect();
            // 守卫：布局未稳时表顶会瞬态贴住主区顶，量出的可用高偏大、会把表格撑爆。
            // 用 top 差值比较——滚动量在差值中抵消，stMain 滚过也能安全重算
            if (resRect.top - mainRect.top < 50) return;
            var pb = parseFloat(getComputedStyle(main).paddingBottom) || 0;
            // 流内末元素底边（相对 main 顶）：alert 可能有多个（删除失败等），取最靠下的
            var flowEnd = resRect.bottom - mainRect.top;
            var alerts = main.querySelectorAll('[data-testid="stAlert"]');
            for (var i = 0; i < alerts.length; i++) {
                var b = alerts[i].getBoundingClientRect().bottom - mainRect.top;
                if (b > flowEnd) flowEnd = b;
            }
            var cur = resRect.height;
            // 缓冲 20px：实测各环境存在与表高无关的幻影占位（alert 外边距等，本机 16px），
            // 定点余量 = 幻影 − 缓冲，缓冲 20 > 16 才能保证 stMain 零溢出、无滚动条
            var avail = cur + (mainRect.height - pb - 20 - flowEnd);
            if (avail >= 100) doc.documentElement.style.setProperty('--list-avail-h', Math.round(avail) + 'px');
        } catch (e) { }
    }
    var _calcT = null;
    function scheduleCalc() { clearTimeout(_calcT); _calcT = setTimeout(calcListHeight, 60); }
    function onWinChange() { sync(); applyFullscreen(); calcListHeight(); }
    sync();
    applyFullscreen();
    window.addEventListener('resize', onWinChange);
    // 关键：本 iframe 在隐藏容器内，父窗口缩放时它自己收不到 resize 事件，
    // 表格高度会一直用旧值（用户环境滚动条/空区问题的根源之一）。
    // 同源 iframe 可直接给父窗口挂监听，窗口/缩放变化都能触发重算。
    try { window.parent.addEventListener('resize', onWinChange); } catch (e) { }
    window.addEventListener('load', function () { sync(); applyFullscreen(); calcListHeight(); });
    // 兜底触发：本 iframe 在 css_inject 隐藏容器内（display:none 不影响执行），
    // 但执行时机可能早于侧边栏渲染——实测会量到未渲染时的全宽 left=0 且此后
    // 无属性变化可再触发。故加延迟重试 + load 事件；下面的 ResizeObserver
    // 负责侧边栏折叠/展开（主区宽度变化）这类不伴随属性变化的布局变动。
    [0, 100, 300, 800, 1500].forEach(function (t) { setTimeout(function () { sync(); applyFullscreen(); calcListHeight(); }, t); });
    var doc = window.parent.document;
    var main = doc && doc.querySelector('section[data-testid="stMain"]');
    if (main && 'ResizeObserver' in window) {
        new ResizeObserver(function () { sync(); calcListHeight(); }).observe(main);
    }
    if (main && 'MutationObserver' in window) {
        // 属性观察：侧边栏折叠/展开（改 main 的 style/class）；
        // childList+subtree：选中行变化会增删 alert（height 随之变）或切换视图，需重算表格高度；
        // characterData：--list-fullscreen 由 fs_state 的 <style> 文本注入（非 :root inline
        // style），其文本变化会触发字符数据突变 → 顺带 applyFullscreen() 切换全屏 class。
        new MutationObserver(function () { applyFullscreen(); scheduleCalc(); }).observe(main, { attributes: true, childList: true, subtree: true, characterData: true, attributeFilter: ['style', 'class'] });
    }
    // Step 3：--list-fullscreen 写在 :root（documentElement）上，故观察它而非 main，
    // 变量一变立即切换全屏 class（不依赖 iframe 是否随 rerun 重执行）
    if (doc && 'MutationObserver' in window) {
        new MutationObserver(function () { applyFullscreen(); }).observe(doc.documentElement, { attributes: true, attributeFilter: ['style'] });
    }
    // ESC 退出全屏：在 parent 文档找到浮动退出按钮并 click（纯前端退出，与 session_state 同步）
    if (doc) {
        doc.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                var v = getComputedStyle(doc.documentElement).getPropertyValue('--list-fullscreen').trim();
                if (v === '1') { var b = doc.querySelector('.st-key-fs_exit button'); if (b) b.click(); }
            }
        });
    }
})();
</script>
""", height=0)

# --- 日志与连接（连接复用：Streamlit 每次 rerun 不重复建连） ---
db.setup_logging()
get_conn = st.cache_resource(db.get_conn)

# --- 会话状态初始化 ---
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'list'   # 'list' 或 'card'（多语言后内部值稳定，显示文本由 i18n 决定）
if 'detail_item_id' not in st.session_state:
    st.session_state.detail_item_id = None
if 'edit_item_id' not in st.session_state:
    st.session_state.edit_item_id = None
if 'selected_indices' not in st.session_state:
    st.session_state.selected_indices = []
if 'tag_filter' not in st.session_state:
    st.session_state.tag_filter = ''
if 'backup_done' not in st.session_state:
    st.session_state.backup_done = False
if 'last_backup' not in st.session_state:
    st.session_state.last_backup = None
if 'orphans' not in st.session_state:
    st.session_state.orphans = None
if 'list_fullscreen' not in st.session_state:
    st.session_state.list_fullscreen = False   # Step 3：列表全屏开关

# --- 数据库连接 ---
conn = get_conn()

# 每会话一次自动备份：放在 init_db（含旧库表结构迁移）之前 —— 迁移会重写表结构，
# 备份必须是迁移前的完整快照（迁移中断可手动恢复）；首次全新库时 db 尚不存在，
# backup_data 跳过 db 只打包 photos，无害。
if not st.session_state.backup_done:
    try:
        st.session_state.last_backup = db.backup_data()
    except Exception as e:
        db.logger.exception("自动备份失败")
        st.warning(i18n.t("app.backup_fail", err=e))
    st.session_state.backup_done = True

# --- 建表/迁移 ---
db.init_db(conn)

# 孤儿图片记录扫描（会话内只查一次）
if st.session_state.orphans is None:
    st.session_state.orphans = db.find_orphan_images(conn)

# 全局容器选项（统一在此查询一次，各 Tab 通过参数共享，不再各自重建）
container_options = repo.get_container_options(conn)

# --- 侧边栏（返回全局筛选条件） ---
search, tag_filter = sidebar.render(conn)

# --- 主界面 ---
st.title(i18n.t("app.main_title"))

# Step 3 全屏态透传：把 session_state 写进 :root 变量（前端 CSS/JS 据此切换全屏）。
# 与 css_inject 同款隐藏容器，避免该 markdown 元素容器占顶部空白。
with st.container(key="fs_state"):
    st.markdown(
        f"<style>:root{{--list-fullscreen:{'1' if st.session_state.list_fullscreen else '0'}}}</style>",
        unsafe_allow_html=True)

# 全屏态浮动退出按钮（常驻 DOM，仅全屏可见；ESC 也触发它，见下方同步 JS）
with st.container(key="fs_exit"):
    if st.button(i18n.t("app.exit_fullscreen"), key="fs_exit_btn"):
        st.session_state.list_fullscreen = False
        st.rerun()

# --- 定义Tabs ---
# 注：Streamlit 1.40 的 st.tabs 不支持 key/on_change（1.55 才引入）。
# 树 Tab 内跨页跳转通过"就地渲染详情页"实现（见 tree_tab.py）。
# Phase 7：「新增物品」不再是独立 Tab，而是「物品浏览」Tab 内的子页面
# （入口按钮在物品 Tab 浏览态顶部），因此原有的 goto_tab 跨 Tab 跳转机制
# （JS 模拟点击 Tab 按钮）随之移除——新增保存后直接在本 Tab 打开详情。
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [i18n.t("app.tab.items"), i18n.t("app.tab.dashboard"), i18n.t("app.tab.timeline"),
     i18n.t("app.tab.tags"), i18n.t("app.tab.tree"),
     i18n.t("app.tab.containers")]
)

with tab1:
    items_tab.render(conn, search, tag_filter, container_options)

with tab2:
    dashboard_tab.render(conn, search, tag_filter)

with tab3:
    timeline_tab.render(conn, search, tag_filter)

with tab4:
    tags_tab.render(conn, search, tag_filter)

with tab5:
    tree_tab.render(conn, search, tag_filter)

with tab6:
    containers_tab.render(conn)
