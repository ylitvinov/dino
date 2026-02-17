
# Kling 3.0 Prompting Guide
**AI Video Generation Guide — 2026 Edition**

## Как писать кинематографические промпты
для модели, понимающей намерение сцены, а не просто список объектов.

### Возможности:
- Мультишот: до 6 кадров
- Нативное аудио и диалоги
- Длительность до 15 секунд
- Высокая точность Image-to-Video

---

## 01 / ВВЕДЕНИЕ
### Модель, понимающая намерение сцены

Kling 3.0 создан для понимания кинематографического замысла, а не просто генерации набора визуальных объектов.

Модель работает лучше всего, когда промпты написаны как режиссёрские указания к сцене. Структура, явное движение и намеренный язык кадра приводят к заметно лучшим результатам.

**Оптимизировано для:**
- сценарных инструкций
- понимания композиции кадра и ритма монтажа
- непрерывности повествования
- передачи эмоций зрителю

### Что указывать в промпте

**Тип кадра и ракурс**
Profile, macro close-up, tracking shot, POV, shot–reverse–shot.

**Поведение камеры**
Описывайте действие во времени: tracking, panning, following, freezing.

**Атмосфера и детали**
Роли персонажей, эмоции, освещение и звуковое окружение сцены.

---

## 02 / ПРИНЦИПЫ
### 3 ключевых принципа промптинга

#### 1️⃣ Думайте шотами, а не клипами
- Kling 3.0 поддерживает сториборды до 6 шотов.
- Явно маркируйте кадры (Shot 1… Shot 6).
- Описывайте фрейминг каждого кадра.

Пример:
[Shot 1: Close-up]  
[Shot 2: Wide angle]

#### 2️⃣ Якорите субъектов рано
- Определяйте персонажей и среду в начале.
- Это сохраняет согласованность внешности.

Совет:
Character A: Navy suit  
Character B: Red dress

#### 3️⃣ Задавайте движение явно
- Описывайте действия и поведение камеры.
- Используйте: tracking, panning, freezing, resuming movement.

Пример:
Camera tracks subject, then freezes on face.

---

## 03 / ДЕТАЛИЗАЦИЯ

### Мультишот и длительность
- До 6 шотов в одном промпте.
- Используйте до 15 секунд для развития сцены.

### Image-to-Video
Используйте изображение как якорь идентичности.  
Описывайте микродвижения, глубину и реакцию камеры.

### Структура промпта

**MASTER PROMPT** — глобальное намерение сцены.  
**SHOT 1 (0–5s)** — начало действия.  
**SHOT 2 (5–10s)** — пик действия.

---

## 05 / АУДИО
### Нативное аудио: как задать диалог

Kling 3.0 поддерживает диалоги, амбиент и контроль эмоций.

**P1. Именование**  
Используйте уникальные метки: [Character A], [Character B]

**P2. Визуальная привязка**  
Опишите действие перед репликой.

**P3. Аудио-детали**  
Указывайте эмоцию и тембр:
[Name, raspy, trembling voice]

**P4. Временной контроль**  
Используйте: Immediately, Pause, Silence

### Пример диалоговой сцены

A detective leans forward slowly.

[Lead Detective, controlled serious voice]:
"Let's stop pretending."

Immediately, the suspect shifts.

[Prime Suspect, sharp defensive voice]:
"I already told you everything."

The detective slides a folder across.  
Paper scraping sound.

[Lead Detective, threatening tone]:
"Then explain this."

---

## 04 / СЛОВАРЬ

### Речь
Speaking, Narrating, Asking

### Эмоции
Whispering, Excitedly speaking, Complaining

### Вокал
A cappella, Pop vocals, Humming, Harmony

### Инструменты
Piano music, Guitar plucking

### SFX
Footsteps, Glass shattering, Bird chirping, Ocean waves, Traffic noise
