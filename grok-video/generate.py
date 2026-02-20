#!/usr/bin/env python3
"""
Генерация длинного видео через Grok Imagine API.
Склейка через последний кадр: каждый следующий клип начинается с последнего кадра предыдущего.

Использование:
  python generate.py --config config.json --api-key YOUR_KEY

config.json:
{
  "initial_image": "start.png",
  "resolution": "720p",
  "duration": 6,
  "crossfade": 0.5,
  "clips": [
    {"prompt": "A dinosaur walking through a forest"},
    {"prompt": "The dinosaur looks up at the sky"},
    {"prompt": "A meteor appears in the sky"}
  ]
}
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time

import requests

API_BASE = "https://api.x.ai/v1"
MODEL = "grok-imagine-video"
POLL_INTERVAL = 5  # секунд между проверками статуса
POLL_TIMEOUT = 600  # макс. ожидание генерации (10 мин)


def submit_video(api_key: str, prompt: str, duration: int, resolution: str, image_path: str | None = None) -> str:
    """Отправляет запрос на генерацию видео, возвращает request_id."""
    body = {
        "model": MODEL,
        "prompt": prompt,
        "duration": duration,
        "resolution": resolution,
    }
    if image_path:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1].lstrip(".").lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
        body["image_url"] = f"data:{mime};base64,{img_b64}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{API_BASE}/videos/generations", json=body, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    request_id = data.get("request_id") or data.get("id")
    if not request_id:
        raise RuntimeError(f"Нет request_id в ответе: {data}")
    print(f"  Запрос отправлен: {request_id}")
    return request_id


def poll_video(api_key: str, request_id: str) -> str:
    """Ждёт завершения генерации, возвращает URL видео."""
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.time()
    retries = 0
    while time.time() - start < POLL_TIMEOUT:
        resp = requests.get(f"{API_BASE}/videos/{request_id}", headers=headers)
        if resp.status_code >= 500:
            retries += 1
            if retries > 5:
                resp.raise_for_status()
            print(f"  Сервер вернул {resp.status_code}, повтор {retries}/5...")
            time.sleep(POLL_INTERVAL * 2)
            continue
        resp.raise_for_status()
        data = resp.json()
        # API возвращает video.url когда готово, без отдельного поля status
        video_url = data.get("video", {}).get("url")
        if video_url:
            return video_url
        status = data.get("status", "")
        if status in ("failed", "error"):
            raise RuntimeError(f"Генерация провалилась: {data}")
        error = data.get("error")
        if error:
            raise RuntimeError(f"Ошибка API: {error}")
        elapsed = int(time.time() - start)
        print(f"  Ожидание... ({elapsed}с)")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Таймаут {POLL_TIMEOUT}с для {request_id}")


def download_video(url: str, output_path: str):
    """Скачивает видео по URL."""
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"  Сохранено: {output_path}")


def extract_last_frame(video_path: str, output_path: str):
    """Извлекает последний кадр из видео."""
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path, "-frames:v", "1", "-q:v", "2", output_path],
        check=True,
        capture_output=True,
    )
    print(f"  Последний кадр: {output_path}")


def concat_videos(clip_paths: list[str], output_path: str, crossfade: float):
    """Склеивает клипы с crossfade."""
    if len(clip_paths) == 1:
        subprocess.run(["cp", clip_paths[0], output_path], check=True)
        return

    if crossfade <= 0:
        # Простая конкатенация без перехода
        list_file = output_path + ".txt"
        with open(list_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path],
            check=True,
            capture_output=True,
        )
        os.remove(list_file)
    else:
        # Цепочка xfade фильтров
        inputs = []
        for p in clip_paths:
            inputs.extend(["-i", p])

        # Получаем длительности клипов
        durations = []
        for p in clip_paths:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                capture_output=True, text=True, check=True,
            )
            durations.append(float(result.stdout.strip()))

        # Строим цепочку xfade
        filter_parts = []
        offsets = []
        cumulative = durations[0]
        for i in range(1, len(clip_paths)):
            offset = cumulative - crossfade
            offsets.append(offset)
            cumulative = offset + durations[i]

        if len(clip_paths) == 2:
            filter_str = f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offsets[0]}[outv]"
        else:
            # Первый xfade
            filter_str = f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offsets[0]}[v1];"
            for i in range(2, len(clip_paths)):
                tag_in = f"v{i-1}"
                tag_out = f"v{i}" if i < len(clip_paths) - 1 else "outv"
                filter_str += f"[{tag_in}][{i}:v]xfade=transition=fade:duration={crossfade}:offset={offsets[i-1]}[{tag_out}];"
            filter_str = filter_str.rstrip(";")

        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[outv]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", output_path]
        subprocess.run(cmd, check=True, capture_output=True)

    print(f"Итоговое видео: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Генерация длинного видео через Grok Imagine API")
    parser.add_argument("--config", required=True, help="Путь к JSON конфигу")
    parser.add_argument("--api-key", help="xAI API ключ (или env XAI_API_KEY)")
    parser.add_argument("--output", default="output.mp4", help="Итоговый файл")
    parser.add_argument("--output-dir", default="clips", help="Папка для промежуточных клипов")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("XAI_API_KEY")
    if not api_key:
        print("Ошибка: укажите --api-key или переменную XAI_API_KEY", file=sys.stderr)
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    initial_image = config.get("initial_image")
    resolution = config.get("resolution", "720p")
    duration = config.get("duration", 6)
    crossfade = config.get("crossfade", 0.5)
    clips_config = config["clips"]

    os.makedirs(args.output_dir, exist_ok=True)

    clip_paths = []
    current_image = initial_image

    for i, clip_cfg in enumerate(clips_config):
        prompt = clip_cfg["prompt"]
        clip_duration = clip_cfg.get("duration", duration)
        clip_path = os.path.join(args.output_dir, f"clip_{i:03d}.mp4")
        frame_path = os.path.join(args.output_dir, f"frame_{i:03d}.jpg")

        print(f"\n=== Клип {i+1}/{len(clips_config)}: {prompt[:60]}... ===")

        # Генерация
        request_id = submit_video(api_key, prompt, clip_duration, resolution, current_image)
        video_url = poll_video(api_key, request_id)
        download_video(video_url, clip_path)

        # Извлечение последнего кадра для следующего клипа
        if i < len(clips_config) - 1:
            extract_last_frame(clip_path, frame_path)
            current_image = frame_path

        clip_paths.append(clip_path)

    # Склейка
    print(f"\n=== Склейка {len(clip_paths)} клипов ===")
    concat_videos(clip_paths, args.output, crossfade)
    total_cost = sum(c.get("duration", duration) for c in clips_config) * 0.05
    print(f"Готово! Примерная стоимость: ${total_cost:.2f}")


if __name__ == "__main__":
    main()
