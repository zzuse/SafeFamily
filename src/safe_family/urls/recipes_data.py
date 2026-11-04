"""Recipes shown on the /recipes page (Sheet section). Edit by hand.

To add a recipe, copy one whole ``{...},`` block below, paste it under the
last one and change the values:

- ``slug``: short unique id used in the page address (/recipes/<slug>), only
  lowercase letters, digits and dashes.
- ``image``: a file in src/safe_family/static/recipes/ (JPG, PNG, WEBP or
  SVG). Leave it as "" for no picture.
- ``ingredients`` and ``steps``: one string per line, in order.
- ``servings``, ``time``, ``tags`` and ``notes`` are optional; use "" or [].

``tests/test_recipes.py`` checks this file (required fields, unique slugs,
pictures that exist), so run ``pytest -q tests/test_recipes.py --no-cov``
after editing. The app reads it at startup: rebuild with
``docker compose up -d --build app``.
"""

RECIPES = [
    {
        "slug": "dou-jiao-men-mian",
        "title": "豆角焖面",
        "summary": "山西豆角焖面是以豆角和面条为核心原料的山西传统家常面食,制作时需先炒制五花肉与豆角,过程中需分次舀出汤汁回淋以保证面条干湿度均匀.山西人食用时注重生蒜佐面,陈醋点睛的搭配,蒜香与酸爽的复合风味成为该菜品的标志性特征",
        "image": "doujiaomenmian.png",
        "servings": "3",
        "time": "60 min",
        "tags": ["dinner", "slow", "vegetarian"],
        "ingredients": [
            "豆角 400g",
            "面条 800g, 以200g面/70g水的比例和面",
            "油 适量",
            "料酒 适量",
            "香油 适量",
            "五花肉 适量",
            "生抽 适量",
            "老抽 适量",
            "蚝油 适量",
            "水 适量",
            "盐 适量",
            "葱 适量",
            "姜 适量",
            "蒜 适量",
        ],
        "steps": [
            "油锅烧热,下入五花肉.放入葱,姜,蒜,爆香.放入料酒",
            "确保五花肉在最下层,倒入掰好的豆角",
            "倒入生抽,老抽,水,盐,焖煮至水开后",
            "转小火焖煮,将面条铺在豆角上,淋少许蚝油",
            "盖上锅盖焖煮面条20分钟.",
            "将锅盖揭开,舀出部分汤汁,淋在面条上,可以适当翻面条,继续焖煮,重复此步骤2-3次,直至面条熟透,汤汁收干,确保肉不被烤煳.",
            "撒上葱花,淋上香油,即可出锅,搅拌均匀后食用.",
        ],
        "notes": "长时间焖煮时,需要保证五花肉在最下面,豆角在中间,面条在最上面.且时刻检查五花肉没有被烤糊",
    },
    {
        "slug": "Dough-Drop-and-Assorted-Vegetable-Soup",
        "title": "Dough Drop and Assorted Vegetable Soup (疙瘩汤)",
        "summary": "疙瘩汤传统做法保留面粉中的维生素B族,符合原汤化原食饮食理念,且因面食类易消化,素汤适合消化功能较弱者作为晚餐食用,也可作为早餐食用.疙瘩汤的做法有很多种,常见的有鸡蛋疙瘩汤,番茄疙瘩汤,豆腐疙瘩汤,酸菜疙瘩汤等.",
        "image": "gedatang.jpeg",
        "servings": "3",
        "time": "15 min",
        "tags": ["dinner", "quick", "vegetarian"],
        "ingredients": [
            "3 tomatoes, cut into wedges",
            "面粉 400g",
            "葱花 适量",
            "鸡蛋 3个",
            "香油 适量",
            "香菜 适量",
            "酱油 适量",
            "salt 盐 适量",
            "水 适量",
            "盐 适量",
            "葱 适量",
        ],
        "steps": [
            "油锅烧热,下入西红柿, 放入葱,姜,蒜,爆香.",
            "加入适量水,煮开后加入盐,酱油调味.",
            "倒入生抽,老抽,水,盐,焖煮至水开后,转小火",
            "白面加入适量水,边加边搅拌,搅拌成疙瘩状,加入锅中",
            "将鸡蛋搅拌成蛋液,",
            "最后转大火,把蛋液和蔬菜加进去,适量盐,白糖,白胡椒粉,香油,香菜调一下味,就可以吃啦",
        ],
        "notes": "用冷水嘀嗒面粉,搅拌成疙瘩状,再放入锅中,这样做出来的疙瘩汤口感更好",
    },
    {
        "slug": "dun-yang-rou",
        "title": "清炖羊肉",
        "summary": "https://baike.baidu.com/item/清炖羊肉/2895309?fromModule=search-result_lemma",
        "image": "dunyangrou.jpeg",
        "servings": "3",
        "time": "50 min",
        "tags": ["dinner", "slow", "meat"],
        "ingredients": [
            "羊前腿,切块 500g",
            "羊腩肉,带白肉 400g",
            "盐 适量",
            "葱 适量",
        ],
        "steps": [
            "冷水焯羊肉,慢慢加热中的浮沫去除,再去掉血水和杂质,捞出冲洗干净",
        ],
        "notes": "挑选带白肉的羊腩肉",
    },
    {
        "slug": "dun-zhu-gan",
        "title": "清炖猪肝",
        "summary": "https://baike.baidu.com/item/炖猪肝?fromModule=lemma_search-box",
        "image": "dunzhugan.jpeg",
        "servings": "3",
        "time": "50 min",
        "tags": ["dinner", "slow", "meat"],
        "ingredients": [
            "猪肝,切块 500g",
            "盐 适量",
            "葱 适量",
        ],
        "steps": [
            "冷水焯肉,再去掉血水和杂质,捞出冲洗干净",
        ],
        "notes": "未知",
    },
]
