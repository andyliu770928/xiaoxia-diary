#!/usr/bin/env python3
"""生成地點照片"""
import os
import sys
import requests
from pathlib import Path

# 讀取 API key
with open("/Users/andyliu/.openclaw/.env") as f:
    for line in f:
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.strip().split("=")[1]

import google.genai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def generate_photo(place_name, outfit_desc):
    prompt = f"""{outfit_desc}, visiting {place_name}, Taipei, anime style, cute girl, happy, warm sunlight, tourist photo"""
    
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    response = model.generate_content(
        prompt,
        generation_config={'response_modalities': ['IMAGE']}
    )
    
    # 取得圖片
    for part in response.candidates[0].content.parts:
        if hasattr(part, 'inline_data') and part.inline_data:
            return part.inline_data.data
    
    return None

if __name__ == "__main__":
    place = sys.argv[1] if len(sys.argv) > 1 else "華山1914"
    photo_data = generate_photo(place, "Cute girl with long brown hair, wearing casual outfit")
    
    if photo_data:
        output = Path(f"/Users/andyliu/clawd/generated/SUMMER/{place}_today.png")
        output.write_bytes(photo_data)
        print(f"✅ 已儲存到：{output}")
    else:
        print("❌ 圖片生成失敗")
