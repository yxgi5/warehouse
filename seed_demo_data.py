# -*- coding: utf-8 -*-
"""演示数据灌入脚本：34 个容器（3 层树）+ 100 个物品 + 按类别配色的测试图片。

用法：
    python seed_demo_data.py        # 库为空时灌入；已有数据则拒绝并提示
    python seed_demo_data.py --fresh  # 先备份现有库，再清空重灌（可复现，random.seed=42）

特点：
- 容器为 3 层树：6 顶层（书房/客厅/卧室/厨房/储物间/玄关）→ 14 二级
  → 14 三级（书架A·上层等细分格、工具箱·常用工具层等），物品全部
  挂在三级叶子容器，容器树 Tab 呈现 顶层→二级→三级→物品 四层行。
- 容器分 6 大类别，每类一个色系，容器照片/物品图颜色跟随类别，
  卡片视图一眼可见差异。
- 物品图 0/1/2 张混布（约 2 成无图、5 成 1 张、3 成 2 张），覆盖
  "无图占位符 / 卡片首图 / 详情页多图画廊 / 图片排序" 全部场景。
- 图片由 PIL 本地生成（渐变底 + 类别图形 + 名称文字），走项目真实
  MIME 校验落盘流程，非伪造文件。
"""
import io
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import repo

# ---------------- 图片生成 ----------------

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
]


def find_font(size, bold=False):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                from PIL import ImageFont
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    from PIL import ImageFont
    return ImageFont.load_default()


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def make_gradient(size, c1, c2, angle=0):
    """垂直(0)/对角(1)双色渐变底图。"""
    from PIL import Image, ImageDraw
    w, h = size
    img = Image.new('RGB', size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        if angle:
            t = (t + 0.5) / 2  # 对角更平缓
        d.line([(0, y), (w, y)], fill=lerp(c1, c2, t))
    return img


def draw_shape(draw, cx, cy, r, kind, fill, outline, width=5):
    """中心画图形：circle/square/triangle/diamond/star。"""
    if kind == 'circle':
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=width)
    elif kind == 'square':
        draw.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=14,
                               fill=fill, outline=outline, width=width)
    elif kind == 'triangle':
        draw.polygon([(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)],
                     fill=fill, outline=outline)
    elif kind == 'diamond':
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                     fill=fill, outline=outline)
    else:  # star（五角星）
        pts = []
        for i in range(10):
            rr = r if i % 2 == 0 else r * 0.45
            ang = -90 + i * 36
            import math
            pts.append((cx + rr * math.cos(math.radians(ang)),
                        cy + rr * math.sin(math.radians(ang))))
        draw.polygon(pts, fill=fill, outline=outline)


def composite(img, overlay):
    """RGBA overlay 叠加到 RGB base（alpha_composite 就地修改）。"""
    from PIL import Image
    out = img.convert('RGBA')
    out.alpha_composite(overlay)
    return out.convert('RGB')


def make_container_image(name, cat_name, location, c1, c2, shape):
    """容器照片 420x300：渐变底 + 半透明图形 + 类别/容器名/位置。"""
    from PIL import Image, ImageDraw
    size = (420, 300)
    img = make_gradient(size, c1, c2, angle=1)
    overlay = Image.new('RGBA', size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    draw_shape(od, 210, 128, 62, shape, (255, 255, 255, 55), (255, 255, 255, 200), 6)
    # 顶部类别条
    od.rounded_rectangle([14, 14, 120, 46], radius=16, fill=(0, 0, 0, 80), outline=(255, 255, 255, 200), width=2)
    d = ImageDraw.Draw(overlay)
    d.text((67, 30), cat_name, font=find_font(18), fill=(255, 255, 255, 235), anchor='mm')
    d.text((210, 208), name, font=find_font(34), fill=(255, 255, 255, 255), anchor='mm')
    d.text((210, 250), location or '', font=find_font(18), fill=(255, 255, 255, 220), anchor='mm')
    buf = io.BytesIO()
    composite(img, overlay).save(buf, 'PNG')
    return buf.getvalue()


def make_item_image(name, item_no, c1, c2, shape):
    """物品图 320x320：渐变底 + 中心图形 + 物品名/item_no。"""
    from PIL import Image, ImageDraw
    size = (320, 320)
    img = make_gradient(size, c1, c2)
    overlay = Image.new('RGBA', size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    draw_shape(od, 160, 130, 78, shape, (255, 255, 255, 60), (255, 255, 255, 200), 6)
    d = ImageDraw.Draw(overlay)
    shown = name if len(name) <= 10 else name[:10] + '…'
    d.text((160, 252), shown, font=find_font(26), fill=(255, 255, 255, 255), anchor='mm')
    d.text((160, 292), item_no, font=find_font(16), fill=(255, 255, 255, 200), anchor='mm')
    buf = io.BytesIO()
    composite(img, overlay).save(buf, 'PNG')
    return buf.getvalue()


class FakeUpload:
    """带 name 的类文件对象，模拟 st.file_uploader 返回值（走真实 MIME 校验落盘）。"""

    def __init__(self, data, name):
        self._buf = io.BytesIO(data)
        self.name = name

    def getbuffer(self):
        return self._buf.getbuffer()


# ---------------- 数据定义 ----------------

# 六大类别色系：(中文类别名, 亮色, 深色, 图形)
CATEGORIES = {
    '书房': ('蓝', '#3b82f6', '#1e3a8a', 'square'),
    '客厅': ('橙', '#f59e0b', '#92400e', 'circle'),
    '卧室': ('紫', '#8b5cf6', '#4c1d95', 'diamond'),
    '厨房': ('绿', '#22c55e', '#14532d', 'triangle'),
    '储物间': ('灰', '#6b7280', '#1f2937', 'star'),
    '玄关': ('青', '#06b6d4', '#155e75', 'square'),
}

# (name, parent, location, category) —— 父容器必须先于子容器（脚本按序反查 id）
# 层级：顶层 6 → 二级 14 → 三级 14，共 34 个；物品全部挂在三级叶子
CONTAINERS = [
    # —— 顶层（6）——
    ('书房', None, '北面房间', '书房'),
    ('客厅', None, '南面客厅', '客厅'),
    ('卧室', None, '主卧', '卧室'),
    ('厨房', None, '西面厨房', '厨房'),
    ('储物间', None, '阳台储物间', '储物间'),
    ('玄关', None, '入户门侧', '玄关'),
    # —— 二级·书房（3）——
    ('书架A', '书房', '东墙，双层书柜', '书房'),
    ('书架B', '书房', '东墙，下层', '书房'),
    ('办公桌抽屉', '书房', '书桌左三抽', '书房'),
    # —— 三级·书架A 细分（2）——
    ('书架A·上层', '书架A', '上层格 1-3', '书房'),
    ('书架A·下层', '书架A', '下层格 4-6', '书房'),
    # —— 二级·客厅（2）——
    ('电视柜', '客厅', '电视下方，两层', '客厅'),
    ('茶几', '客厅', '沙发前', '客厅'),
    # —— 三级·电视柜 细分（2）——
    ('电视柜·抽屉1', '电视柜', '左侧抽屉', '客厅'),
    ('电视柜·抽屉2', '电视柜', '右侧抽屉', '客厅'),
    # —— 二级·卧室（2）——
    ('衣柜', '卧室', '主卧东墙', '卧室'),
    ('床头柜', '卧室', '床左侧', '卧室'),
    # —— 三级·衣柜 细分（2）——
    ('衣柜·挂衣区', '衣柜', '左半边挂衣杆', '卧室'),
    ('衣柜·叠放区', '衣柜', '右半边层板', '卧室'),
    # —— 二级·厨房（2）——
    ('橱柜上层', '厨房', '水槽上方吊柜', '厨房'),
    ('橱柜下层', '厨房', '灶台下方', '厨房'),
    # —— 三级·橱柜上层 细分（2）——
    ('橱柜上层·左柜', '橱柜上层', '左侧吊柜', '厨房'),
    ('橱柜上层·右柜', '橱柜上层', '右侧吊柜', '厨房'),
    # —— 二级·储物间（3）——
    ('收纳箱组1', '储物间', 'A 架 1-2 层', '储物间'),
    ('收纳箱组2', '储物间', 'A 架 3 层', '储物间'),
    ('工具箱', '储物间', 'B 架底层', '储物间'),
    # —— 三级·收纳箱组1 细分（2）——
    ('收纳箱组1·箱A', '收纳箱组1', 'A1 箱', '储物间'),
    ('收纳箱组1·箱B', '收纳箱组1', 'A2 箱', '储物间'),
    # —— 三级·工具箱 细分（2，树的最深分支）——
    ('工具箱·常用工具层', '工具箱', '上层托盘', '储物间'),
    ('工具箱·备用耗材层', '工具箱', '下层抽屉', '储物间'),
    # —— 二级·玄关（2）——
    ('鞋柜', '玄关', '入户右侧', '玄关'),
    ('置物架', '玄关', '入户左侧', '玄关'),
    # —— 三级·鞋柜 细分（2）——
    ('鞋柜·常穿层', '鞋柜', '中层开放格', '玄关'),
    ('鞋柜·收纳层', '鞋柜', '下层带门格', '玄关'),
]

# 容器 -> 物品列表：(name, price, platform, features, description, tags)
# 物品全部挂在叶子容器（三级/四级），非叶子容器（书架A/电视柜等）只作分组。
ITEMS = {
    '书架A·上层': [
        ('深入理解计算机系统', 89.0, '京东', 'CSAPP 第三版', '计算机系统经典教材', '纸质,可借出'),
        ('代码大全（第2版）', 108.0, '京东', '软件构建经典', '程序员必读', '纸质'),
        ('设计模式：可复用面向对象', 62.0, '淘宝', 'GoF 经典', '面向对象设计参考', '纸质,可借出'),
        ('SQLite 权威指南', 56.0, '淘宝', '数据库参考', '本地数据库手册', '纸质'),
    ],
    '书架A·下层': [
        ('Streamlit 应用开发实战', 79.0, '京东', 'Python 数据应用', '学写数据应用', '纸质'),
        ('人类简史', 68.0, '拼多多', '社科畅销', '从动物到上帝', '纸质,可借出'),
        ('三体全集', 128.0, '京东', '科幻三部曲', '刘慈欣代表作', '纸质,可借出'),
        ('原子习惯', 52.0, '淘宝', '自我管理', '习惯养成方法论', '纸质'),
    ],
    '书架B': [
        ('进击的巨人 1-10 合订', 210.0, '淘宝', '漫画合订本', '巨人典藏合集', '纸质'),
        ('灌篮高手 完全版', 298.0, '京东', '典藏漫画', '井上雄彦完全版', '纸质,贵重'),
        ('海贼王 1-20', 240.0, '闲鱼', '二手漫画', '草帽团前中期', '纸质,旧物待处理'),
        ('国家地理 2023 合订', 88.0, '线下', '杂志合订', '全年 12 期', '纸质'),
        ('科幻世界 2024 全年', 96.0, '淘宝', '杂志订阅', '中文科幻月刊', '纸质'),
        ('孤独星球·日本', 45.0, '京东', '旅行指南', '关西关东攻略', '纸质,可借出'),
        ('DK 博物大百科', 158.0, '京东', '儿童科普', '自然百科全书', '纸质,贵重'),
    ],
    '办公桌抽屉': [
        ('罗技 MX Master 3S 鼠标', 649.0, '京东', '无线/静音', '办公旗舰鼠标', '电子,贵重,保修期内'),
        ('三星 T7 1TB 移动硬盘', 659.0, '京东', 'Type-C/便携', '高速备份盘', '电子,贵重'),
        ('闪迪 64G U盘 ×3', 135.0, '淘宝', '便携', '应急文件拷贝', '电子'),
        ('得力计算器 DL-837', 25.0, '线下', '12位', '财务计算', '电子'),
        ('晨光中性笔 0.5mm 整盒', 28.0, '淘宝', '办公耗材', '黑色 60 支装', '纸质'),
        ('回形针/长尾夹套装', 19.9, '京东', '办公用品', '桌面收纳', '纸质'),
        ('倍思 65W 氮化镓充电器', 129.0, '京东', '快充/小巧', '手机笔记本通用', '电子,充电设备'),
    ],
    '电视柜·抽屉1': [
        ('Apple TV 4K 三代', 1189.0, '京东', '4K/HDR', '客厅流媒体盒子', '电子,贵重'),
        ('索尼 PS5 光驱版', 3899.0, '京东', '游戏主机', '客厅娱乐主力', '电子,贵重,保修期内'),
        ('华为 Sound X 音箱', 999.0, '京东', '智能音箱', '帝瓦雷低音', '电子,贵重'),
        ('森海塞尔 HD599 耳机', 1299.0, '京东', '开放头戴', '家庭影院级听感', '电子,贵重,保修期内'),
    ],
    '电视柜·抽屉2': [
        ('Switch Pro 手柄', 459.0, '淘宝', '无线', '游戏配件', '电子'),
        ('小米盒子 4S', 299.0, '京东', '4K 播放器', '备用电视盒子', '电子'),
        ('绿联 HDMI 2.1 线 2m', 89.0, '淘宝', '8K 线材', '高清连接', '电子'),
        ('罗技 Harmony 遥控器', 349.0, '闲鱼', '万能遥控', '多设备合一', '电子,旧物待处理'),
    ],
    '茶几': [
        ('宜家马克杯 ×4', 39.9, '线下', '陶瓷', '日常水杯', '玻璃,易碎'),
        ('玻璃凉水壶 1.5L', 49.0, '淘宝', '玻璃', '夏日饮品', '玻璃,易碎'),
        ('陶瓷茶具套装', 199.0, '京东', '陶瓷', '壶+4 杯待客', '玻璃,易碎,贵重'),
        ('木制托盘', 45.0, '闲鱼', '实木', '桌几收纳', '旧物待处理'),
        ('皮质纸巾盒', 29.9, '淘宝', '皮质', '客厅用品', ''),
        ('零食收纳罐 ×3', 35.0, '拼多多', '塑料密封', '防潮存零食', '需防潮'),
    ],
    '衣柜·挂衣区': [
        ('优衣库轻薄羽绒服', 499.0, '线下', '保暖/可收纳', '冬季外套', '旧物待处理'),
        ('驼色羊毛大衣', 899.0, '线下', '冬季正装', '羊毛混纺', '旧物待处理,可借出'),
        ('运动速干T恤 ×5', 199.0, '京东', '速干', '健身衣物', '可借出'),
        ('羊绒围巾', 299.0, '线下', '保暖', '冬季配饰', '可借出'),
    ],
    '衣柜·叠放区': [
        ('无印良品四件套', 399.0, '京东', '纯棉/亲肤', '床品套装', '需防潮'),
        ('真丝枕套 ×2', 158.0, '淘宝', '真丝', '护发枕套', '需防潮'),
        ('透明防尘罩 ×10', 69.0, '淘宝', '防尘', '衣物收纳', '需防潮'),
    ],
    '床头柜': [
        ('小米智能闹钟', 129.0, '京东', '语音/闹钟', '床头时钟', '电子'),
        ('飞利浦睡眠眼罩', 89.0, '淘宝', '真丝/遮光', '助眠', '可借出'),
        ('被讨厌的勇气', 39.8, '京东', '纸质', '睡前读物', '纸质'),
        ('无印良品香薰机', 298.0, '京东', '超声波/静音', '助眠加湿', '电子,易碎'),
        ('磁吸床头阅读灯', 99.0, '淘宝', '磁吸/充电', '阅读照明', '电子,充电设备'),
        ('褪黑素软糖', 45.0, '淘宝', '膳食补充', '助眠', '需防潮'),
    ],
    '橱柜上层·左柜': [
        ('双立人不粘煎锅 28cm', 399.0, '京东', '不粘/导热', '厨房主力锅', '易碎'),
        ('Bialetti 摩卡壶', 158.0, '淘宝', '意式咖啡', '咖啡器具', '易碎,贵重'),
        ('竹制砧板 ×2', 59.0, '淘宝', '竹制', '切菜板', '需防潮'),
        ('手动打蛋器', 15.0, '线下', '不锈钢', '烘焙工具', ''),
    ],
    '橱柜上层·右柜': [
        ('苏泊尔电饭煲 4L', 289.0, '京东', '预约/不粘', '日常米饭', '电子,保修期内'),
        ('玻璃保鲜盒 5件套', 119.0, '京东', '玻璃', '剩菜收纳', '玻璃,易碎'),
        ('厨房电子秤 0.1g', 69.0, '京东', '精准', '烘焙计量', '电子'),
        ('防潮米箱 10kg', 89.0, '京东', '密封', '大米储存', '需防潮'),
    ],
    '橱柜下层': [
        ('五常大米 10kg', 89.9, '京东', '当季新米', '主食储备', '需防潮'),
        ('山茶油 5L', 158.0, '京东', '低温压榨', '食用油', '需防潮'),
        ('生抽/老抽套装', 49.9, '淘宝', '酿造', '调味品', '需防潮'),
        ('香菇干货 500g', 65.0, '淘宝', '干货', '炖汤提鲜', '需防潮'),
        ('意大利面 ×6', 54.0, '拼多多', '意面囤货', '主食', '需防潮'),
        ('火锅底料 ×10', 79.0, '淘宝', '川味', '家庭火锅', '需防潮'),
        ('九阳料理机', 349.0, '京东', '破壁/豆浆', '厨房电器', '电子,易碎,保修期内'),
    ],
    '收纳箱组1·箱A': [
        ('无印良品收纳箱 大 ×4', 356.0, '京东', '可叠放', '衣物收纳', '需防潮'),
        ('羊毛毯（双人）', 299.0, '线下', '保暖', '冬季盖毯', '旧物待处理'),
        ('电热毯（双控）', 189.0, '京东', '双控温', '冬季取暖', '电子,充电设备'),
        ('樟脑丸/防潮袋套装', 39.9, '京东', '防蛀', '收纳防虫', '需防潮'),
    ],
    '收纳箱组1·箱B': [
        ('凉席 1.5m', 129.0, '淘宝', '竹席', '夏季床品', '旧物待处理'),
        ('蒙古包蚊帐', 79.0, '拼多多', '免安装', '夏季防蚊', ''),
        ('记忆棉枕头 ×2', 199.0, '京东', '护颈', '睡眠用品', '需防潮'),
        ('夏凉被（水洗棉）', 149.0, '淘宝', '可水洗', '夏季盖被', '需防潮'),
    ],
    '收纳箱组2': [
        ('乐高城市系列', 899.0, '京东', '颗粒积木', '收藏拼装', '贵重,可借出'),
        ('乐高机械组 911', 1099.0, '京东', '科技系列', '拼装收藏', '贵重'),
        ('桌游·卡坦岛', 268.0, '淘宝', '策略桌游', '聚会娱乐', '可借出'),
        ('桌游·璀璨宝石', 199.0, '京东', '入门桌游', '聚会娱乐', '可借出'),
        ('拼图 1000 片 ×3', 117.0, '淘宝', '减压', '打发时间', ''),
        ('大号风筝', 45.0, '线下', '户外', '春日玩具', '旧物待处理'),
        ('儿童积木桌', 329.0, '京东', '学习桌', '儿童玩具', '可借出'),
    ],
    '工具箱·常用工具层': [
        ('博世 12V 电钻', 499.0, '京东', '无绳/扭矩', '家用钻孔', '电子,贵重,保修期内'),
        ('史丹利 47 件工具套装', 329.0, '京东', '组合工具', '家修常备', ''),
        ('世达扳手套装', 149.0, '淘宝', '铬钒钢', '维修工具', ''),
        ('羊角锤', 35.0, '线下', '钢制', '敲击工具', ''),
    ],
    '工具箱·备用耗材层': [
        ('卷尺 5m ×2', 25.0, '线下', '钢卷尺', '测量', ''),
        ('绝缘胶带/扎带包', 22.0, '淘宝', '耗材', '电工辅料', ''),
    ],
    '鞋柜·常穿层': [
        ('耐克 Air Max 270', 699.0, '京东', '缓震', '通勤跑鞋', '可借出'),
        ('阿迪达斯 Ultraboost', 599.0, '闲鱼', '回弹', '跑步鞋', '旧物待处理,可借出'),
        ('其乐乐福鞋', 899.0, '线下', '真皮', '通勤皮鞋', '可借出,贵重'),
        ('回力帆布鞋', 69.0, '淘宝', '复古', '日常休闲', '旧物待处理'),
    ],
    '鞋柜·收纳层': [
        ('骆驼徒步鞋', 349.0, '淘宝', '防水', '户外徒步', '可借出'),
        ('浴室拖鞋 ×4', 59.0, '拼多多', '防滑 EVA', '浴室用品', ''),
        ('鞋撑/除臭剂套装', 45.0, '京东', '收纳', '鞋子保养', '需防潮'),
        ('干鞋器', 79.0, '淘宝', '烘干', '冬季速干', '电子,充电设备'),
    ],
    '置物架': [
        ('小米电动螺丝刀', 159.0, '京东', '电动', '家庭维修', '电子,充电设备'),
        ('双肩背包 15.6寸', 299.0, '京东', '防泼水', '通勤背包', '可借出'),
        ('天堂伞 加大款', 45.0, '线下', '防风', '雨天出行', ''),
        ('木质钥匙收纳盒', 29.0, '淘宝', '木质', '玄关收纳', ''),
        ('无线门铃', 89.0, '京东', '免布线', '居家安防', '电子'),
        ('高筒雨鞋 ×2', 99.0, '拼多多', '防水', '雨天通勤', '需防潮'),
        ('便携折叠凳', 55.0, '淘宝', '承重', '排队应急', ''),
    ],
}

PLATFORM_PREFIX = {'京东': 'JD', '淘宝': 'TB', '拼多多': 'PDD', '闲鱼': 'XY', '线下': 'OFF'}


# ---------------- 灌入 ----------------

def main():
    fresh = '--fresh' in sys.argv
    conn = db.get_conn()
    db.init_db(conn)
    n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    n_cons = conn.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
    if (n_items or n_cons) and not fresh:
        print(f"库里已有数据（items={n_items}, containers={n_cons}）。")
        print("如需清空重灌请加 --fresh（会先备份现有库）：python seed_demo_data.py --fresh")
        return

    # 1. 备份现有库（fresh 模式下保底）
    db.setup_logging()
    backup = db.backup_data(keep=1)
    print(f"已备份现有数据 → {os.path.basename(backup)}")

    # 2. 清空（容器 parent_id 自引用 RESTRICT，整表删除需临时关外键；与 migrate_schema 同法）
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        for t in ('images', 'item_tags', 'tags', 'items', 'container_images', 'containers'):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    # 3. 容器（父容器先建，get_container_options 反查 id）
    cid_by_name = {}
    for name, parent, location, cat in CONTAINERS:
        repo.add_container(conn, name, cid_by_name.get(parent), location)
        cid_by_name[name] = conn.execute(
            "SELECT id FROM containers WHERE name=?", (name,)).fetchone()[0]
    print(f"容器 {len(cid_by_name)} 个已建")

    # 4. 容器照片（每容器 1 张，按类别配色）
    for name, parent, location, cat in CONTAINERS:
        cat_label, light, dark, shape = CATEGORIES[cat]
        png = make_container_image(name, f"{cat} · {cat_label}", location, hex2rgb(light), hex2rgb(dark), shape)
        repo.save_container_images(conn, cid_by_name[name],
                                   [FakeUpload(png, f"{name}.png")])
    print(f"容器照片 {len(CONTAINERS)} 张已生成")

    # 5. 物品（编号 ITEM_20260820_001~100；图片 0/1/2 张混布）
    random.seed(42)
    seq = 0
    img_cnt = 0
    item_no_images = 0
    item_two_images = 0
    tag_stats = {}
    date_pool = [(2023, 4), (2023, 11), (2024, 3), (2024, 9), (2025, 2), (2025, 6), (2026, 1), (2026, 5)]

    for cname, items in ITEMS.items():
        parent_cat = next(c[3] for c in CONTAINERS if c[0] == cname)
        _, light, dark, _ = CATEGORIES[parent_cat]
        for (nm, price, platform, feats, desc, tags) in items:
            seq += 1
            item_no = f"ITEM_20260820_{seq:03d}"
            y, m = random.choice(date_pool)
            pdate = f"{y}-{m:02d}-{random.randint(1, 27):02d}"
            order_no = f"{PLATFORM_PREFIX.get(platform, 'XX')}{random.randint(10**8, 10**9 - 1)}"
            # 图片分配：序号 % 5 == 0 → 无图；否则 0/1/2 张交替（seed 固定可复现）
            n = 0 if seq % 5 == 0 else (1 if seq % 3 != 0 else 2)
            imgs = []
            for k in range(n):
                shape = 'circle' if '电子' in tags else ('square' if '纸质' in tags
                         else ('diamond' if '玻璃' in tags else 'triangle'))
                png = make_item_image(nm, item_no, hex2rgb(light), hex2rgb(dark), shape)
                imgs.append(FakeUpload(png, f"{item_no}_{k + 1}.png"))
            repo.add_item(conn, item_no, nm, cid_by_name[cname], pdate, platform,
                          order_no, price, feats, desc, tags, imgs)
            img_cnt += n
            if n == 0:
                item_no_images += 1
            elif n == 2:
                item_two_images += 1
            for t in (x.strip() for x in tags.split(',') if x.strip()):
                tag_stats[t] = tag_stats.get(t, 0) + 1

    # 6. 统计（树形打印容器层级与物品分布）
    print(f"物品 {seq} 个已灌入")
    print(f"  图片：物品图 {img_cnt} 张（1 张={seq - item_no_images - item_two_images} 个，2 张={item_two_images} 个，无图={item_no_images} 个）")
    tags = sorted(conn.execute("SELECT name FROM tags").fetchall())
    print(f"标签 {len(tags)} 个：{', '.join(n for (n,) in tags)}")
    children_map = {}
    for name, parent, _loc, _cat in CONTAINERS:
        children_map.setdefault(parent, []).append(name)

    def subtree_total(name):
        """递归统计该容器子树全部物品数（含各级子容器）。"""
        return len(ITEMS.get(name, [])) + sum(subtree_total(k) for k in children_map.get(name, []))

    def dump_tree(parent, level, prefix=""):
        kids = children_map.get(parent, [])
        for i, name in enumerate(kids):
            is_last = i == len(kids) - 1
            branch = "└ " if is_last else "├ "
            print("  " * level + prefix + branch + f"{name}（{subtree_total(name)} 件）")
            dump_tree(name, level + 1, prefix + ("   " if is_last else "│  "))

    dump_tree(None, 0)

    # 7. 自检：孤儿图片应为 0
    orphans = db.find_orphan_images(conn)
    print(f"孤儿图片自检：{len(orphans)} 条（应为 0）")
    conn.close()
    print("DONE")


if __name__ == '__main__':
    main()
