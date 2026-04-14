#!/usr/bin/env python3
"""生成地點照片 - 與小夏日常生圖同一風格"""
import os
import random
import re
import subprocess
import sys
from pathlib import Path

# 改到 automation 目錄才能引用小夏的 prompt 建構系統
_AUTOMATION_DIR = Path("/Users/andyliu/clawd/automation")
sys.path.insert(0, str(_AUTOMATION_DIR))

from xiaoxia_prompt_builder import (
    KYOTO_ANIMATION_STYLE_KEY,
    build_full_prompt,
    compose_prompt_parts,
    build_character_base_prompt,
    build_minimax_model_hint,
    build_render_guard_prompt,
)
from xiaoxia_prompt_components import (
    build_designer_outfit,
    build_girlfriend_expression,
    build_long_hair_style,
    build_safe_pose,
    build_scene_detail_prompt,
    summarize_location_context,
)
from xiaoxia_morning_report import (
    generate_xiaoxia_image,
    read_state,
)

# ---------- 地點搜尋（豐富場景描述） ----------
TAVILY_SCRIPT = _AUTOMATION_DIR / "skills" / "openclaw-tavily-search" / "scripts" / "tavily_search.py"
_location_cache = {}


def search_location(location: str) -> str:
    """用 Tavily 搜尋地點特色，回傳豐富的場景描述"""
    if location in _location_cache:
        return _location_cache[location]
    if not TAVILY_SCRIPT.exists():
        return ""
    query = f"{location} 景點 特色 畫面"
    try:
        proc = subprocess.run(
            [sys.executable, str(TAVILY_SCRIPT),
             "--query", query, "--max-results", "1",
             "--include-answer", "--search-depth", "basic", "--format", "raw"],
            capture_output=True, text=True, timeout=8,
        )
        import json as _json
        data = _json.loads(proc.stdout)
        lines = []
        if data.get("answer"):
            lines.append(data["answer"].strip())
        for r in (data.get("results") or [])[:1]:
            content = r.get("content", "").strip()
            if content:
                lines.append(content)
        result = " ".join(lines[:2])
        _location_cache[location] = result
        return result
    except Exception:
        return ""


# ---------- 場景 → 穿搭風格對照 ----------
SCENE_OUTFIT_RULES = [
    (("陽明山", "山", "郊外", "步道", "公園", "花季", "賞花"),
     "designer outdoor date styling with a sculpted knit top, a soft wrap skirt or slim shorts, "
     "a light cropped windbreaker, soft neutral tones, and pretty travel-date details"),
    (("咖啡廳", "咖啡店", "甜點店", "餐廳", "下午茶"),
     "designer cafe date styling with an asymmetrical knit or square-neck blouse, "
     "a pleated or wrap skirt, a cropped blazer or refined cardigan, and boutique-label details"),
    (("海邊", "海灘", "海岸", "沙灘", "泳池", "福隆"),
     "designer resort-date styling with a breezy sundress or draped halter top, "
     "a layered skirt or tailored shorts, a light cover-up, and airy feminine details"),
    (("夜市", "市區", "信義區", "街頭", "逛街", "商場", "西門町"),
     "designer city-date styling with a fitted asymmetrical top or soft camisole, "
     "a sharp mini skirt or tailored shorts, a cropped jacket, and polished urban details"),
    (("羽球", "羽毛球", "球場", "體育館", "運動", "健身", "慢跑", "跑步", "籃球"),
     "designer athleisure date styling with a fitted sporty top, "
     "a pleated tennis skirt or clean athletic shorts, a premium warm-up layer, "
     "and flattering sporty details"),
    (("老街", "九份", "迪化街", "剝皮寮", "龍山寺"),
     "designer retro-date styling with a square-neck knit top, "
     "a soft plaid mini skirt, a cropped cardigan, low heels, "
     "and small vintage-inspired accessories"),
    (("貓空", "內湖", "象山", "步道", "郊山"),
     "designer hiking-date styling with a fitted breathable top, "
     "slim hiking pants or sporty shorts, a light windbreaker, "
     "and comfortable trail-ready details"),
    (("博物館", "美术馆", "華山", "松菸", "北藝中心"),
     "designer gallery-date styling with an elegant knit top, "
     "a structured wrap skirt, a short tailored blazer, "
     "low heels and polished cultural-date accessories"),
    (("河邊", "河濱", "大稻埕", "淡水", "基隆河"),
     "designer riverside-date styling with a breezy knit top, "
     "a flowing mini skirt, a light layer, and relaxed waterfront details"),
]

# ---------- 場景 → 京都動畫風格背景描述 ----------
SCENE_STYLE_TEMPLATES = {
    "default":    "outdoor anime environment with layered details, natural daylight, gentle breeze, clear atmospheric depth, Kyoto Animation style background",
    "cafe":       "cozy cafe interior or terrace with warm ambient lighting, soft golden tones, wooden furniture, visible coffee cups, Kyoto Animation style interior with warm pastel colors",
    "beach":      "seaside location with visible shoreline, textured sky, gentle sea breeze, soft warm sunlight, Kyoto Animation style seaside with bright saturated colors",
    "city":       "lively urban street with storefronts, neon signs, evening lights, pedestrian atmosphere, layered street details, Kyoto Animation style city with vibrant colors",
    "mountain":   "mountain path with trees, gentle slopes, filtered sunlight, fresh air atmosphere, layered hillside depth, Kyoto Animation style outdoor with natural greens",
    "old_street": "old street lane with red lanterns, stone steps, traditional shop facades, hanging signs, warm late-afternoon shadows, Kyoto Animation style retro street with layered environmental detail",
    "museum":      "museum plaza with clean architectural lines, broad steps, open sky, subtle banners, modern facade, late-afternoon shadows, Kyoto Animation style architectural background with refined depth",
    "riverside":  "riverside path with railing, distant bridge, swaying grass, broad sky, soft breeze, warm late-afternoon sunlight, Kyoto Animation style riverside with readable horizon and layered depth",
}


def classify_scene_type(scene_hint: str) -> str:
    if any(k in scene_hint for k in ("咖啡廳", "咖啡店", "甜點", "餐廳", "下午茶")): return "cafe"
    if any(k in scene_hint for k in ("海邊", "海灘", "海岸", "沙灘", "泳池", "福隆")): return "beach"
    if any(k in scene_hint for k in ("夜市", "市區", "信義", "街頭", "西門")): return "city"
    if any(k in scene_hint for k in ("陽明山", "山", "郊外", "步道", "貓空", "內湖", "象山")): return "mountain"
    if any(k in scene_hint for k in ("老街", "九份", "迪化", "剝皮", "龍山寺")): return "old_street"
    if any(k in scene_hint for k in ("博物館", "美术馆", "華山", "松菸", "北藝")): return "museum"
    if any(k in scene_hint for k in ("河邊", "河濱", "大稻埕", "淡水", "基隆")): return "riverside"
    return "default"


def get_outfit_for_scene(scene_hint: str) -> str:
    for keywords, outfit in SCENE_OUTFIT_RULES:
        if any(k in scene_hint for k in keywords):
            return outfit
    return build_designer_outfit(scene_hint or "default")


def get_scene_style(scene_hint: str) -> str:
    return random.choice([
        SCENE_STYLE_TEMPLATES.get(classify_scene_type(scene_hint), SCENE_STYLE_TEMPLATES["default"])
    ])


# ---------- Prompt 建構核心（與平常生圖同一水準） ----------
def build_place_photo_prompt(
    place_name: str,
    location_context: str = "",
    extra_hint: str = "",
):
    """建構景點照片的完整 prompt。回傳 (gemini_prompt, minimax_prompt)"""

    # 各項 prompt 元件
    hair_style      = build_long_hair_style(place_name, fallback_home=False)
    expression_hint = build_girlfriend_expression(place_name, fallback_home=False, is_night=False)
    outfit_hint     = get_outfit_for_scene(place_name)
    pose_hint       = build_safe_pose(place_name, fallback_home=False)
    camera_angle    = "wide environmental shot with generous background, full body with scenic depth"
    scene_style     = get_scene_style(place_name)
    scene_detail    = build_scene_detail_prompt(place_name, is_night=False, fallback_home=False)
    location_detail = summarize_location_context(place_name, location_context)
    extra_scene     = search_location(place_name)
    accessory       = "a delicate necklace, small stud earrings"

    outfit_guard = (
        "outfit styling must clearly match the environment, "
        "with believable scene-appropriate materials and mood, "
        "while still looking fashion-forward and intentionally styled"
    )
    lighting = "warm afternoon outdoor light with soft natural atmosphere"
    composition = (
        "wide environmental portrait composition, full body or three-quarter body from moderate distance, "
        "subject occupies roughly 30 to 45 percent of the frame, "
        "expansive readable surroundings with layered foreground midground and background depth"
    )
    background_priority = (
        "background-first travel photo language, emphasize rich environment storytelling, "
        "clear foreground objects, readable midground details, distant background, "
        "subject smaller in frame, avoid close-up composition"
    )
    reference_hint = (
        "Xiaoxia's face and hairstyle must stay consistent with reference images. "
        "Mature young adult appearance, not childlike."
    )
    # 禁文字出現（圖片生成時避免亂碼文字）
    no_text_guard = (
        "IMPORTANT: No text, no characters, no words, no symbols, no captions, "
        "no labels, and no written language of any kind should appear anywhere in the image. "
        "The scene must contain no written text whatsoever."
    )

    combined_extra = ", ".join(filter(None, [
        reference_hint,
        extra_hint,
        no_text_guard,
        f"place: {place_name}",
    ]))

    # Gemini-style（完整版，用於 Cloudflare fallback）
    gemini_prompt = build_full_prompt(
        hair_style=hair_style,
        expression_hint=expression_hint,
        outfit_hint=outfit_hint,
        accessory_hint=accessory,
        activity_hint="",
        pose_hint=pose_hint,
        camera_angle_hint=camera_angle,
        scene_style=scene_style,
        scene_detail=", ".join(filter(None, [scene_detail, location_detail, extra_scene])),
        outfit_guard=outfit_guard,
        lighting=lighting,
        composition=composition,
        background_priority=background_priority,
        narrative_hint="Xiaoxia visiting a Taipei location, shared with Andy as a travel-date photo",
        extra_hint=combined_extra,
        style_key=KYOTO_ANIMATION_STYLE_KEY,
    )

    # MiniMax-style（濃縮版，用於 image-01）
    minimax_prompt = compose_prompt_parts(
        build_character_base_prompt(hair_style, expression_hint, style_key=KYOTO_ANIMATION_STYLE_KEY),
        f"wearing {outfit_hint}",
        accessory,
        "",
        pose_hint,
        camera_angle,
        "",
        scene_style,
        ", ".join(filter(None, [scene_detail, location_detail, extra_scene])),
        outfit_guard,
        lighting,
        composition,
        background_priority,
        combined_extra,
        build_minimax_model_hint(style_key=KYOTO_ANIMATION_STYLE_KEY),
        build_render_guard_prompt(style_key=KYOTO_ANIMATION_STYLE_KEY),
    )

    return gemini_prompt, minimax_prompt


# ---------- 景點心得生成 ----------
TRAVEL_MOOD_TEMPLATES = {
    "default": [
        "這裡的氣氛很舒服，陽光剛剛好，不會太刺，我忍不住慢慢走了一圈。",
        "第一次來這裡，環境比我預想的還好，散步起來特別放鬆。",
        "我在這裡站了一下，看著周圍的景色，覺得心情跟著景色一起開闊起來。",
    ],
    "beach": [
        "海風吹過來的時候，整個人都輕了一點，特別舒服。",
        "聽著海浪的聲音，會有一種時間慢下來的感覺，很喜歡。",
        "沙灘上有點暖，走起來很放鬆，我還偷偷踢了幾下水。",
    ],
    "cafe": [
        "選了一個靠窗的位置坐了一下，光線剛好，整個人都跟著慢下來了。",
        "咖啡廳的氣氛很安靜，我在這裡待了一會，思緒也跟著沉澱下來。",
        "聞到咖啡香就有一種被好好對待的感覺，很喜歡這種小確幸。",
    ],
    "mountain": [
        "走著走著，視線越來越遠，心情也跟著越來越開闊。",
        "山上的空氣特別乾淨，深呼吸的時候會有一種被大自然寵到的感覺。",
        "慢慢往上走的過程很舒服，流一點汗之後反而更放鬆。",
    ],
    "city": [
        "熱鬧的街道逛起來很有趣，到處都有東西可以看，一點都不無聊。",
        "城市的光線和顏色很豐富，隨便走走都有新的發現。",
        "我在街角站了一會，看著人來人往，有一種參與感很強的快樂。",
    ],
    "old_street": [
        "老街的氣氛很特別，有一種時間累積出來的溫度，很耐人尋味。",
        "巷弄裡處處是驚喜，隨便一個角落都有故事感，我拍了很多張。",
        "走在老街裡，會有一種被歷史包圍的感覺，很奇妙的體驗。",
    ],
    "museum": [
        "展覽的空間很舒服，走進去的時候會有一種需要安靜下來的氛圍。",
        "在博物館裡慢慢走，突然覺得時間過得特別慢，但那種慢是好的。",
        "藝術品的細節讓人忍不住想靠近多看幾眼，每一步都有新發現。",
    ],
    "riverside": [
        "河邊的風很溫柔，我沿著步道走，看著水面反射的光，心情特別平靜。",
        "在水邊的時候，會有一種把自己交出去的放鬆感，很舒服。",
        "河景開闊，空氣也好，我在這裡站了很久，看水、看天、看遠方的橋。",
    ],
}


def generate_travel_mood(place_name: str, scene_type: str) -> str:
    """根據地點與場景類型，生成小夏的遊玩心得"""
    pool = TRAVEL_MOOD_TEMPLATES.get(scene_type, TRAVEL_MOOD_TEMPLATES["default"])

    # 加入地點特色關鍵字，讓心得更有「個人化」感
    place_mood_modifiers = {
        "福隆": "海水、沙灘、海風",
        "九份": "老街、階梯、紅燈籠",
        "淡水": "夕陽、河邊、碼頭",
        "陽明山": "山景、花季、步道",
        "華山": "文創、紅磚、老建築",
        "大稻埕": "老街、布莊、迪化街",
        "象山": "城市view、階梯、夜景",
        "貓空": "纜車、茶園、山景",
    }
    modifier = ""
    for key, mod in place_mood_modifiers.items():
        if key in place_name:
            modifier = mod
            break

    base_mood = random.choice(pool)

    if modifier:
        # 把基礎心得配上地點特色，變成更具體的個人化描述
        return f"{base_mood} ({modifier})"

    return base_mood
def main():
    place = sys.argv[1] if len(sys.argv) > 1 else "華山1914文化園區"
    extra_hint = ""
    if "--hint" in sys.argv:
        idx = sys.argv.index("--hint")
        extra_hint = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""

    print(f"📍 正在為「{place}」生成小夏遊照...")

    gemini_prompt, minimax_prompt = build_place_photo_prompt(place, extra_hint=extra_hint)

    try:
        state = read_state()
        generation = generate_xiaoxia_image(
            prompt=gemini_prompt,
            state=state,
            minimax_prompt=minimax_prompt,
            scene_reference_base64=None,
            flow="place_photo",
        )

        from xiaoxia_morning_report import save_xiaoxia_generated_image
        import shutil

        img_path = save_xiaoxia_generated_image(generation, gemini_prompt)

        safe_name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", place).strip("_")
        timestamp = int(Path(__file__).stat().st_mtime)
        final_path = Path(f"/Users/andyliu/clawd/generated/SUMMER/place_{safe_name}_{timestamp}.png")
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(img_path, Path):
            shutil.copy(img_path, final_path)
        else:
            import requests as _req
            r = _req.get(generation["image_url"], timeout=30)
            r.raise_for_status()
            final_path.write_bytes(r.content)

        print(f"✅ 已儲存到：{final_path}")
        print(f"🎞️  模型：{generation.get('model')} / {generation.get('source')}")

        # 順便產生小夏遊玩心得
        scene_type = classify_scene_type(place)
        mood = generate_travel_mood(place, scene_type)
        print(f"💬 {mood}")

    except Exception as e:
        print(f"❌ 生圖失敗：{e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())