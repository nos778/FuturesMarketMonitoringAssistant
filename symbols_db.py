"""内置期货品种字典 — 覆盖中国期货市场全部6大交易所期货品种。
Sina 行情 API 约定：全部大写 + "0" 表示连续主力合约。
支持交易所: SHFE / INE / DCE / CZCE / GFEX / CFFEX
"""

# 品种定义：(sina_code, 中文名, 交易所, 板块)
SYMBOLS = [
    # ---- 上海期货交易所 (SHFE) ---- 17个
    ("RB0",  "螺纹钢",     "SHFE", "黑色系"),
    ("HC0",  "热轧卷板",   "SHFE", "黑色系"),
    ("SS0",  "不锈钢",     "SHFE", "黑色系"),
    ("AU0",  "黄金",       "SHFE", "贵金属"),
    ("AG0",  "白银",       "SHFE", "贵金属"),
    ("CU0",  "铜",         "SHFE", "有色金属"),
    ("AL0",  "铝",         "SHFE", "有色金属"),
    ("ZN0",  "锌",         "SHFE", "有色金属"),
    ("NI0",  "镍",         "SHFE", "有色金属"),
    ("PB0",  "铅",         "SHFE", "有色金属"),
    ("SN0",  "锡",         "SHFE", "有色金属"),
    ("AO0",  "氧化铝",     "SHFE", "有色金属"),
    ("RU0",  "橡胶",       "SHFE", "化工"),
    ("FU0",  "燃料油",     "SHFE", "能源"),
    ("BU0",  "沥青",       "SHFE", "能源"),
    ("SP0",  "纸浆",       "SHFE", "化工"),
    ("BR0",  "丁二烯橡胶", "SHFE", "化工"),

    # ---- 上海国际能源交易中心 (INE) ---- 4个
    ("SC0",  "原油",       "INE",  "能源"),
    ("LU0",  "低硫燃油",   "INE",  "能源"),
    ("NR0",  "20号胶",     "INE",  "化工"),
    ("BC0",  "国际铜",     "INE",  "有色金属"),

    # ---- 大连商品交易所 (DCE) ---- 21个
    ("I0",   "铁矿石",     "DCE",  "黑色系"),
    ("J0",   "焦炭",       "DCE",  "黑色系"),
    ("JM0",  "焦煤",       "DCE",  "黑色系"),
    ("M0",   "豆粕",       "DCE",  "农产品"),
    ("Y0",   "豆油",       "DCE",  "农产品"),
    ("P0",   "棕榈油",     "DCE",  "农产品"),
    ("C0",   "玉米",       "DCE",  "农产品"),
    ("CS0",  "玉米淀粉",   "DCE",  "农产品"),
    ("A0",   "豆一",       "DCE",  "农产品"),
    ("B0",   "豆二",       "DCE",  "农产品"),
    ("JD0",  "鸡蛋",       "DCE",  "农产品"),
    ("LH0",  "生猪",       "DCE",  "农产品"),
    ("RR0",  "粳米",       "DCE",  "农产品"),
    ("PP0",  "聚丙烯",     "DCE",  "化工"),
    ("L0",   "塑料",       "DCE",  "化工"),
    ("V0",   "PVC",        "DCE",  "化工"),
    ("EB0",  "苯乙烯",     "DCE",  "化工"),
    ("EG0",  "乙二醇",     "DCE",  "化工"),
    ("PG0",  "液化石油气", "DCE",  "化工"),
    ("FB0",  "纤维板",     "DCE",  "林产品"),
    ("BB0",  "胶合板",     "DCE",  "林产品"),

    # ---- 郑州商品交易所 (CZCE) ---- 20个
    ("CF0",  "棉花",       "CZCE", "农产品"),
    ("CY0",  "棉纱",       "CZCE", "农产品"),
    ("SR0",  "白糖",       "CZCE", "农产品"),
    ("OI0",  "菜油",       "CZCE", "农产品"),
    ("RM0",  "菜粕",       "CZCE", "农产品"),
    ("AP0",  "苹果",       "CZCE", "农产品"),
    ("CJ0",  "红枣",       "CZCE", "农产品"),
    ("PK0",  "花生",       "CZCE", "农产品"),
    ("TA0",  "PTA",        "CZCE", "化工"),
    ("MA0",  "甲醇",       "CZCE", "化工"),
    ("SA0",  "纯碱",       "CZCE", "化工"),
    ("FG0",  "玻璃",       "CZCE", "化工"),
    ("UR0",  "尿素",       "CZCE", "化工"),
    ("PF0",  "短纤",       "CZCE", "化工"),
    ("PX0",  "对二甲苯",   "CZCE", "化工"),
    ("SH0",  "烧碱",       "CZCE", "化工"),
    ("PL0",  "丙烯",       "CZCE", "化工"),
    ("PR0",  "瓶片",       "CZCE", "化工"),
    ("SF0",  "硅铁",       "CZCE", "黑色系"),
    ("SM0",  "锰硅",       "CZCE", "黑色系"),

    # ---- 广州期货交易所 (GFEX) ---- 3个
    ("SI0",  "工业硅",     "GFEX", "新能源材料"),
    ("LC0",  "碳酸锂",     "GFEX", "新能源材料"),
    ("PS0",  "多晶硅",     "GFEX", "新能源材料"),

    # ---- 中国金融期货交易所 (CFFEX) ---- 8个
    # 股指期货: 09:30-11:30, 13:00-15:00, 无夜盘
    ("IF0",  "沪深300期指", "CFFEX", "金融"),
    ("IH0",  "上证50期指",  "CFFEX", "金融"),
    ("IC0",  "中证500期指", "CFFEX", "金融"),
    ("IM0",  "中证1000期指","CFFEX", "金融"),
    # 国债期货: 09:15-11:30, 13:00-15:15, 无夜盘
    ("T0",   "10年国债",    "CFFEX", "金融"),
    ("TF0",  "5年国债",     "CFFEX", "金融"),
    ("TS0",  "2年国债",     "CFFEX", "金融"),
    ("TL0",  "30年国债",    "CFFEX", "金融"),
]

# 交易所列表
EXCHANGES = {
    "SHFE": "上海期货交易所",
    "INE":  "上海国际能源交易中心",
    "DCE":  "大连商品交易所",
    "CZCE": "郑州商品交易所",
    "GFEX": "广州期货交易所",
    "CFFEX": "中国金融期货交易所",
}

# 板块列表
CATEGORIES = ["黑色系", "贵金属", "有色金属", "能源", "化工", "农产品", "新能源材料", "林产品", "金融"]

# 快捷品种列表（用于合约浏览按钮）：(代码, 中文名, 板块)
SHORTCUT_VARIETIES = [
    # 黑色系 (8)
    ("RB", "螺纹钢", "黑色系"), ("HC", "热卷", "黑色系"), ("SS", "不锈钢", "黑色系"),
    ("I", "铁矿石", "黑色系"), ("J", "焦炭", "黑色系"), ("JM", "焦煤", "黑色系"),
    ("SF", "硅铁", "黑色系"), ("SM", "锰硅", "黑色系"),
    # 贵金属 (2)
    ("AU", "黄金", "贵金属"), ("AG", "白银", "贵金属"),
    # 有色金属 (8)
    ("CU", "铜", "有色金属"), ("AL", "铝", "有色金属"), ("ZN", "锌", "有色金属"),
    ("NI", "镍", "有色金属"), ("PB", "铅", "有色金属"), ("SN", "锡", "有色金属"),
    ("AO", "氧化铝", "有色金属"), ("BC", "国际铜", "有色金属"),
    # 能源 (4)
    ("SC", "原油", "能源"), ("LU", "低硫燃油", "能源"),
    ("FU", "燃料油", "能源"), ("BU", "沥青", "能源"),
    # 化工 (19)
    ("RU", "橡胶", "化工"), ("NR", "20号胶", "化工"), ("BR", "丁二烯", "化工"),
    ("SP", "纸浆", "化工"), ("MA", "甲醇", "化工"), ("TA", "PTA", "化工"),
    ("PP", "聚丙烯", "化工"), ("L", "塑料", "化工"), ("V", "PVC", "化工"),
    ("EB", "苯乙烯", "化工"), ("EG", "乙二醇", "化工"), ("PG", "液化气", "化工"),
    ("SA", "纯碱", "化工"), ("FG", "玻璃", "化工"), ("UR", "尿素", "化工"),
    ("PF", "短纤", "化工"), ("PX", "对二甲苯", "化工"), ("SH", "烧碱", "化工"),
    ("PL", "丙烯", "化工"), ("PR", "瓶片", "化工"),
    # 农产品 (17)
    ("M", "豆粕", "农产品"), ("Y", "豆油", "农产品"), ("P", "棕榈油", "农产品"),
    ("C", "玉米", "农产品"), ("CS", "淀粉", "农产品"), ("A", "豆一", "农产品"),
    ("B", "豆二", "农产品"), ("JD", "鸡蛋", "农产品"), ("LH", "生猪", "农产品"),
    ("RR", "粳米", "农产品"), ("CF", "棉花", "农产品"), ("CY", "棉纱", "农产品"),
    ("SR", "白糖", "农产品"), ("OI", "菜油", "农产品"), ("RM", "菜粕", "农产品"),
    ("AP", "苹果", "农产品"), ("CJ", "红枣", "农产品"), ("PK", "花生", "农产品"),
    # 新能源材料 (3)
    ("SI", "工业硅", "新能源材料"), ("LC", "碳酸锂", "新能源材料"), ("PS", "多晶硅", "新能源材料"),
    # 林产品 (2)
    ("FB", "纤维板", "林产品"), ("BB", "胶合板", "林产品"),
    # 金融 (8)
    ("IF", "沪深300期指", "金融"), ("IH", "上证50期指", "金融"),
    ("IC", "中证500期指", "金融"), ("IM", "中证1000期指", "金融"),
    ("T", "10年国债", "金融"), ("TF", "5年国债", "金融"),
    ("TS", "2年国债", "金融"), ("TL", "30年国债", "金融"),
]


def get_symbol_dict():
    """返回 {sina_code: {name, exchange, category}} 字典"""
    return {code: {"name": name, "exchange": exch, "category": cat}
            for code, name, exch, cat in SYMBOLS}


def get_by_exchange(exchange):
    """按交易所过滤品种列表"""
    return [(c, n, e, cat) for c, n, e, cat in SYMBOLS if e == exchange]


def search(keyword):
    """模糊搜索品种，返回匹配列表"""
    kw = keyword.strip().upper()
    return [(c, n, e, cat) for c, n, e, cat in SYMBOLS
            if kw in c or kw in n.upper() or kw in c.upper()]


def get_variety_prefix(code):
    """从合约代码提取品种前缀，如 RB2610 → RB, RB0 → RB"""
    result = ""
    for ch in code.upper():
        if ch.isalpha():
            result += ch
        else:
            break
    return result


def guess_exchange(code):
    """根据合约代码推测交易所"""
    prefix = get_variety_prefix(code)
    for sym_code, name, exch, cat in SYMBOLS:
        if get_variety_prefix(sym_code) == prefix:
            return exch
    # 默认规则：按品种前缀范围判断
    shfe_prefixes = {"RB", "HC", "SS", "AU", "AG", "CU", "AL", "ZN", "NI", "PB",
                     "SN", "AO", "RU", "FU", "BU", "SP", "BR"}
    ine_prefixes = {"SC", "LU", "NR", "BC"}
    dce_prefixes = {"I", "J", "JM", "M", "Y", "P", "C", "CS", "A", "B",
                    "JD", "LH", "RR", "PP", "L", "V", "EB", "EG", "PG", "FB", "BB"}
    czce_prefixes = {"CF", "CY", "SR", "OI", "RM", "AP", "CJ", "PK",
                     "TA", "MA", "SA", "FG", "UR", "PF", "PX", "SH", "PL", "PR",
                     "SF", "SM"}
    gfex_prefixes = {"SI", "LC", "PS"}
    cffex_prefixes = {"IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"}
    if prefix in shfe_prefixes:
        return "SHFE"
    if prefix in ine_prefixes:
        return "INE"
    if prefix in dce_prefixes:
        return "DCE"
    if prefix in czce_prefixes:
        return "CZCE"
    if prefix in gfex_prefixes:
        return "GFEX"
    if prefix in cffex_prefixes:
        return "CFFEX"
    return ""


def get_name_by_code(code):
    """根据合约代码获取品种中文名"""
    prefix = get_variety_prefix(code)
    for sym_code, name, exch, cat in SYMBOLS:
        if get_variety_prefix(sym_code) == prefix:
            return name
    return code
