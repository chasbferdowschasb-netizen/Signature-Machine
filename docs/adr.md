# SIGNATURE MACHINE

## MASTER PROJECT RULES & CONSOLIDATED ARCHITECTURE

**Document Type:** Master Project Rules / Architecture / Reference Standard
**Project:** Signature Machine
**Repository:** `Signature-Machine`
**Status:** CONFIRMED / REFERENCE DOCUMENT
**Current Knowledge Version:** `0.3`
**Current Reference Samples:** `25`
**Immutable Archive:** `sample_000001` → `sample_000024`
**New Sample Policy:** `sample_000025+`
**Last Consolidated:** 2026-08-24

---

# 1. PURPOSE OF THIS DOCUMENT

این سند مرجع اصلی قوانین، استانداردها، تصمیمات معماری و اصول توسعه پروژه **Signature Machine** است.

هدف آن این است که تصمیمات تأییدشده در اسناد قبلی در یک سند واحد جمع شوند تا:

* قوانین پروژه پراکنده نباشند.
* تصمیمات معماری قبلی دوباره تغییر نکنند.
* توسعه‌دهندگان بعدی بدانند چه چیزهایی قطعی هستند.
* از ساخت فایل‌ها و موتورهای موازی جلوگیری شود.
* Dataset و Knowledge موجود بدون دلیل تخریب یا بازسازی اشتباه نشوند.
* Sampleهای جدید استانداردهای قبلی را به‌صورت خودکار به ارث ببرند.
* مسیر توسعه Generation Engine بر اساس Knowledge موجود انجام شود.

این سند باید به‌عنوان **مرجع تصمیم‌گیری پروژه** در توسعه‌های بعدی مورد استفاده قرار گیرد.

---

# 2. PROJECT GOAL

هدف Signature Machine ساخت سیستمی است که بتواند با استفاده از مجموعه‌ای از نمونه‌های تأییدشده، **سبک، ساختار، قواعد هندسی و قواعد حرکتی امضا** را یاد بگیرد و بر اساس آن برای نام‌ها و مشتریان جدید امضاهای جدید طراحی کند.

هدف پروژه صرفاً تقلید یک تصویر ثابت نیست.

سیستم نهایی باید بتواند موارد زیر را یاد بگیرد:

* سبک کلی امضا
* ساختار هندسی
* نسبت طول و عرض
* فرم کلی
* تعداد Strokeها
* ترتیب Strokeها
* مسیر حرکت قلم
* سرعت
* فشار
* جهت
* انحنا
* Timing
* فاصله بین Strokeها
* تراکم خطوط
* نحوه ترکیب اجزای نام
* ترکیب فارسی و انگلیسی
* ویژگی‌های گرافیکی امضا
* ویژگی‌های حرکتی امضا

Generation باید بتواند از این دانش برای ساخت نمونه‌های جدید استفاده کند.

---

# 3. DEFINITION OF A USABLE SIGNATURE

یک خروجی قابل استفاده نباید صرفاً:

* تصویر متن با فونت دست‌نویس،
* کپی یک نمونه قبلی،
* یا یک Random Drawing

باشد.

یک Signature قابل استفاده باید:

1. بر اساس دانش آموخته‌شده از Reference Dataset طراحی شده باشد.
2. از نظر Style با فضای نمونه‌های مرجع سازگار باشد.
3. از نظر ساختار Strokeها معتبر باشد.
4. از نظر حرکت و مسیر قلم منطقی باشد.
5. به‌عنوان یک طراحی مستقل قابل استفاده باشد.
6. حداقل خروجی PNG داشته باشد.
7. اطلاعات فنی آن قابل ذخیره و بازیابی باشد.

---

# 4. REFERENCE KNOWLEDGE

تمام نمونه‌هایی که توسط صاحب پروژه تأیید می‌شوند، بخشی از **Reference Knowledge** پروژه هستند.

هیچ نمونه تأییدشده‌ای صرفاً به دلیل:

* نام پوشه،
* شماره Sample،
* داشتن Label،
* یا نوع امضا

از نظر ارزش یادگیری بالاتر یا پایین‌تر از نمونه دیگر محسوب نمی‌شود.

## قانون قطعی

هر Sample تأییدشده باید:

* وارد Reference Dataset شود.
* برای تحلیل استفاده شود.
* برای استخراج Feature استفاده شود.
* برای Knowledge Update قابل استفاده باشد.
* در آینده در Generation مورد استفاده قرار گیرد.

---

# 5. MASTER / APPROVED POLICY

مفهوم قدیمی:

```text
MASTER/
APPROVED/
```

از نظر ارزش یادگیری معتبر نیست.

پروژه نباید Sampleها را از نظر دانش یادگیری به MASTER و APPROVED تقسیم کند.

مدل مرجع:

```text
Reference Learning
└── samples/
    ├── sample_000001/
    ├── sample_000002/
    ├── ...
    └── sample_XXXXXX/
```

هر Sample تأییدشده یک عضو معتبر Reference Knowledge است.

---

# 6. CURRENT REFERENCE DATASET

وضعیت فعلی تأییدشده:

```text
Knowledge Version: 0.3
Reference Samples: 25
Processed: 25
Failed: 0
```

نمونه‌های فعلی:

```text
sample_000001
...
sample_000025
```

Knowledge موجود با موفقیت از ابتدا برای هر 25 نمونه rebuild شده است.

---

# 7. IMMUTABLE ARCHIVE: SAMPLES 001–024

Sampleهای:

```text
sample_000001
...
sample_000024
```

به‌عنوان آرشیو مرجع تأییدشده تثبیت شده‌اند.

این آرشیو نباید برای اعمال تغییرات جدید پروژه بازطراحی یا دستکاری شود، مگر اینکه در آینده یک تصمیم صریح و جدید برای تغییر آن صادر شود.

استانداردهای تثبیت‌شده این آرشیو شامل:

* PNG
* Video
* Practice PDF
* Raw Stroke Data
* Package Structure

است.

تغییرات جدید باید روی Sampleهای جدید اعمال شوند، نه با بازنویسی آرشیو 001–024.

---

# 8. SAMPLE 025+ INHERITANCE RULE

از:

```text
sample_000025
```

به بعد، هر Sample جدید باید تمام استانداردهای تأییدشده Sampleهای 001–024 را به ارث ببرد.

علاوه بر آن، تنظیمات جدید و تأییدشده پروژه نیز باید روی Sampleهای جدید اعمال شوند.

این تنظیمات شامل:

* Pressure-based rendering
* Fountain Pen profile
* Smooth Rendering
* Centered Video
* PNG استاندارد
* Practice PDF
* Automated Customer Package
* Manifest

است.

بنابراین:

```text
Sample 025+
=
Previous Approved Standards
+
New Confirmed Standards
```

---

# 9. LABEL POLICY

وجود Label برای یادگیری الزامی نیست.

Dataset باید بتواند هر دو نوع Sample را نگهداری کند:

```text
Labeled Sample
```

و:

```text
Unlabeled Sample
```

Label می‌تواند شامل مواردی مانند:

* فقط اسم
* فقط فامیل
* اسم + فامیل
* فارسی
* انگلیسی
* فارسی + انگلیسی
* انگلیسی + فارسی
* یا سایر ترکیب‌ها

باشد.

---

# 10. UNLABELED SAMPLES

`unlabeled` بودن به معنی بی‌ارزش بودن Sample نیست.

برخی امضاها ممکن است صرفاً طراحی گرافیکی باشند و وابستگی مستقیمی به نام نداشته باشند.

این نمونه‌ها باید برای یادگیری موارد زیر استفاده شوند:

* Shape
* Style
* Geometry
* Stroke Structure
* Motion
* Composition
* Graphic Signature Design

بنابراین Knowledge باید حداقل دو نوع دانش را پوشش دهد:

```text
Text-conditioned Signature Design
```

و:

```text
Shape / Style-conditioned Signature Design
```

---

# 11. NAME INPUT POLICY

Generation آینده باید بتواند با حالت‌های مختلف نام کار کند:

```text
First Name Only
Last Name Only
First + Last Name
Persian + English
English + Persian
Persian + Persian
English + English
Mixed / Other
Unknown / Shape-only
```

سیستم نباید برای یک قالب نام خاص طراحی شود.

---

# 12. RAW DATA IS AUTHORITATIVE

داده خام حرکت قلم باید حفظ شود.

فایل اصلی:

```text
strokes.json
```

می‌تواند شامل:

```text
x
y
time_ms
pressure
pointer_type
buttons
tilt_x
tilt_y
twist
stroke order
```

باشد.

اصل اساسی:

```text
RAW DATA ≠ DISPLAY RENDER
```

هرگونه:

* Smooth
* Render
* Visual Processing
* PNG Generation

نباید جایگزین داده خام شود.

---

# 13. SAMPLE CORE STRUCTURE

ساختار پایه Sample:

```text
sample_XXXXXX/
├── raw.png
├── render.png
├── strokes.json
├── metadata.json
└── CUSTOMER_PACKAGE/
    ├── 01_FINAL_ASSETS/
    │   ├── 01_FINAL_BLACK_ON_WHITE.png
    │   ├── 02_BLACK_TRANSPARENT.png
    │   ├── 03_WHITE_ON_BLACK.png
    │   └── 04_WHITE_TRANSPARENT.png
    └── 02_TRAINING/
        ├── 01_TRAINING.mp4
        └── 01_PRACTICE.pdf
```

همراه Package:

```text
package_manifest.json
```

---

# 14. RAW.PNP / RAW IMAGE POLICY

`raw.png` تصویر خام/مرجع تصویری Sample است.

وجود آن نباید باعث شود که داده Stroke حذف یا نادیده گرفته شود.

داده‌های حرکتی باید مستقل از Render نگهداری شوند.

---

# 15. METADATA POLICY

`metadata.json` باید اطلاعات خلاصه و فنی Sample را نگهداری کند.

موارد نمونه:

```text
sample_id
label
point_count
stroke_count
duration
pressure information
pointer type
creation information
```

Metadata بخشی از بسته مرجع Sample است.

---

# 16. PNG STANDARD

استاندارد تأییدشده خروجی PNG:

```text
2400 × 1359
```

برای هر Sample استاندارد چهار خروجی باید تولید شود:

```text
01_FINAL_BLACK_ON_WHITE.png
02_BLACK_TRANSPARENT.png
03_WHITE_ON_BLACK.png
04_WHITE_TRANSPARENT.png
```

این استاندارد برای Sampleهای 025+ نیز الزامی است.

---

# 17. TRAINING VIDEO STANDARD

فایل استاندارد:

```text
01_TRAINING.mp4
```

مشخصات:

```text
1336 × 512
60 FPS
```

ویدیو باید:

* امضا را در مرکز قرار دهد.
* مستقل از محل رسم روی Canvas باشد.
* ترتیب واقعی Strokeها را حفظ کند.
* Idle Gapهای غیرضروری را حذف کند.
* خروجی باکیفیت تولید کند.

---

# 18. PRACTICE PDF STANDARD

فایل تمرینی باید:

```text
A4
20 samples
4 columns × 5 rows
```

باشد.

معیار نهایی PDF، **چاپ واقعی روی کاغذ A4** است، نه صرفاً نمایش روی مانیتور.

نمونه‌ها باید برای تمرین دستی:

* به اندازه کافی بزرگ،
* خوانا،
* و قابل چاپ

باشند.

---

# 19. FOUNTAIN PEN / PRESSURE STANDARD

برای Sampleهای جدید، Pressure قلم در Render باید قابل استفاده باشد.

مدل مفهومی:

```text
Pressure Variation
        ↓
Line Width Variation
        ↓
Fountain Pen Appearance
```

پروفایل فعلی:

```text
fountain_pen_v1
```

پارامترهای ثبت‌شده:

```text
baseline: 0.85
pressure_gain: 3.35
pressure_curve: 0.82
```

این تنظیمات بخشی از استاندارد Sampleهای جدید هستند.

---

# 20. SMOOTH RENDERING RULE

Smooth Rendering فقط برای:

* Display
* Render
* Replay
* Output Generation

است.

Smooth نباید داده خام Stroke را تغییر دهد.

هدف:

```text
Reduce visual curve fragmentation
WITHOUT
Artificially changing original signature form
```

قبل از هر تغییر در Smooth باید فایل HTML واقعی مورد استفاده بررسی شود.

نباید بدون بررسی فایل واقعی فرض شود که تابع خاصی با نام مشخص وجود دارد.

---

# 21. TOUCH POINT POLICY

وجود `touch` نباید به‌صورت خودکار به معنی:

```text
Noise
Error
Invalid Input
```

تلقی شود.

در امضاهای فارسی، نقاط حروف می‌توانند Touch واقعی باشند.

سیستم باید بین:

```text
Real Letter Touch
```

و:

```text
Accidental / Unwanted Touch
```

تمایز ایجاد کند.

تا زمانی که چنین تشخیصی وجود ندارد، Touch نباید صرفاً به دلیل وجود آن حذف شود.

---

# 22. SAVE / APPROVAL RULE

هیچ Sample صرفاً به دلیل رسم شدن روی Canvas وارد Dataset نمی‌شود.

فرآیند صحیح:

```text
DRAW
   ↓
REVIEW
   ↓
USER APPROVES
   ↓
SAVE
   ↓
REFERENCE DATASET
```

اگر کاربر طرح را رد کند:

```text
DRAW
   ↓
DISCARD
   ↓
NOTHING ENTERS REFERENCE DATASET
```

Sample ردشده نباید:

* در Dataset ذخیره شود.
* به Server ارسال شود.
* وارد Knowledge شود.

---

# 23. ONE SAVE → ONE COMPLETE PACKAGE

از Sample 025 به بعد، Save موفق باید تمام Package استاندارد را ایجاد کند.

فرآیند:

```text
User Draws
    ↓
SAVE REFERENCE
    ↓
Create Sample
    ↓
Raw Data
    ↓
Render
    ↓
4 × PNG
    ↓
Training Video
    ↓
Practice PDF
    ↓
Manifest
    ↓
Complete Customer Package
```

اصل قطعی:

> ONE SAVE → ONE COMPLETE PACKAGE

کاربر نباید مجبور باشد برای هر Artifact عملیات جداگانه انجام دهد.

---

# 24. UNIQUE SAMPLE ID

هر Save موفق باید یک Sample ID غیرتکراری ایجاد کند.

فرمت:

```text
sample_XXXXXX
```

مثلاً:

```text
sample_000025
sample_000026
sample_000027
```

شماره Sample نباید تکراری شود.

---

# 25. REPLAY POLICY

Replay برای بازسازی نحوه ترسیم امضا است.

Replay باید:

* Strokeها را به ترتیب واقعی اجرا کند.
* مسیر را تدریجی نمایش دهد.
* در صورت استفاده از Smooth، فقط Render/Display را Smooth کند.
* داده اصلی را تغییر ندهد.
* پایان Replay را مشخص کند.

Replay جایگزین Undo/Redo نیست.

---

# 26. UNDO / REDO POLICY

Undo و Redo برای ویرایش History طراحی هستند.

رفتار مورد انتظار:

```text
DRAW
  ↓
UNDO
  ↓
REDO
```

Undo باید آخرین Stroke یا وضعیت قبلی History را برگرداند.

Redo باید امکان بازگرداندن وضعیت Undo شده را فراهم کند.

این قابلیت باید History-based باشد و صرفاً به یک:

```python
strokes.pop()
```

محدود نشود.

Replay و Undo/Redo دو قابلیت متفاوت هستند.

---

# 27. REFERENCE FEATURE EXTRACTION

Feature Extraction باید روی Reference Dataset انجام شود.

خروجی فعلی:

```text
analysis/reference_features.json
```

Feature Extraction باید Read-Only باشد و Dataset اصلی را تغییر ندهد.

---

# 28. REFERENCE FEATURES

ویژگی‌های پایه شامل:

## Geometry

```text
width
height
aspect_ratio
bounding_box
```

## Stroke

```text
stroke_count
point_count
```

## Motion

```text
duration
distance
average_speed
maximum_speed
```

## Pressure

```text
minimum_pressure
maximum_pressure
mean_pressure
pressure_variance
```

## Input

```text
pointer_type
touch_information
```

---

# 29. KNOWLEDGE 0.3

Knowledge فعلی با نسخه:

```text
REFERENCE_KNOWLEDGE_VERSION = "0.3"
```

تثبیت شده است.

Profileهای اصلی:

```text
Geometry
Velocity
Pressure
Direction
Curvature
```

همچنین Knowledge شامل ویژگی‌های ساختاری مانند:

```text
stroke_count
point_count
touch_point_count
path_length
active_time_ms
mean_speed
mean_direction_change
pressure_mean
pressure_variance
inter_stroke_gaps_ms
stroke_duration_statistics
stroke_path_length_statistics
stroke_speed_statistics
```

است.

---

# 30. PROFILE RESAMPLING RULE

برای جلوگیری از مشکل اختلاف طول Profileها، Profileهای Scalar قبل از Aggregation باید به طول ثابت Resample شوند.

مقدار فعلی:

```text
RESAMPLE_POINTS = 32
```

Profileهای مرتبط:

```text
velocity
pressure
direction
curvature
```

این اصلاح باعث شده Knowledge مربوط به 25 Sample بدون خطا Rebuild شود.

---

# 31. WELFORD AGGREGATION

Aggregation فعلی از Welford aggregation استفاده می‌کند.

Profileهای اصلی پس از Rebuild باید Countهای سازگار داشته باشند.

تفاوت Count در Stroke Indexهای بالاتر طبیعی است، زیرا همه Sampleها تعداد Stroke یکسان ندارند.

بنابراین اختلاف تعداد نمونه‌ها در Strokeهای شماره بالاتر به‌خودی‌خود خطا محسوب نمی‌شود.

---

# 32. ANALYZER VS FEATURE EXTRACTOR

این دو مسئولیت نباید با هم ادغام یا به موتورهای موازی تبدیل شوند.

### Reference Analyzer

مسئول:

* بررسی Dataset
* گزارش آماری
* مقایسه Featureها
* بررسی Touch
* بررسی Geometry
* بررسی Motion
* بررسی Pressure

### Reference Feature Extractor

مسئول:

* استخراج Featureهای قابل استفاده برای Knowledge/Generation

هر دو ابزار باید Read-Only باشند.

---

# 33. TOOL RESPONSIBILITY RULE

اصل معماری:

> ONE RESPONSIBILITY PER EXISTING TOOL

اما این اصل به معنی:

> ONE NEW FILE PER RESPONSIBILITY

نیست.

برای قابلیت جدید ابتدا باید بررسی شود آیا ابزار یا Engine موجود قابلیت انجام آن را دارد یا خیر.

---

# 34. NO PARALLEL ENGINE RULE

ساخت موتورهای موازی و همپوشان ممنوع است.

نباید معماری به چیزی مانند این تبدیل شود:

```text
geometry_engine.py
pressure_engine.py
velocity_engine.py
visual_engine.py
learning_engine.py
analysis_engine.py
stroke_engine.py
render_engine.py
png_engine.py
...
```

Capabilityهای مرتبط باید داخل معماری اصلی قرار گیرند.

---

# 35. FINAL CORE ARCHITECTURE

معماری تأییدشده پروژه:

```text
SIGNATURE MACHINE
        |
        v
      CORE
        |
        +----------------------+
        |                      |
        v                      v
KNOWLEDGE ENGINE       GENERATION ENGINE
```

پروژه حداکثر شامل:

```text
1 Core
2 Main Engines
```

است.

---

# 36. CORE OWNERSHIP RULE

Core مالک اصلی سیستم است.

Core مسئول:

* Orchestration
* Control
* Workflow
* Lifecycle
* Validation Flow
* Coordination

است.

هیچ Engine دیگری مالک سیستم نیست.

هیچ Engine دیگری نباید تبدیل به Orchestrator بالادست شود.

---

# 37. KNOWLEDGE ENGINE

Knowledge Engine مسئول تمام فعالیت‌های مرتبط با دانش است.

Capabilityهای آن شامل:

```text
Data Acquisition
Visual Analysis
Structural Analysis
Motion Analysis
Feature Extraction
Learning
Aggregation
Knowledge Update
Knowledge Validation
```

همچنین:

```text
Geometry
Stroke Structure
Stroke Order
Stroke Count
Trajectory
Velocity
Pressure
Direction
Curvature
Timing
Inter-stroke Gaps
Bounding Box
Proportions
Pen Dynamics
```

متعلق به Knowledge Engine هستند.

Visual Recognition نیز بخشی از Knowledge Engine است و نباید به موتور مستقل تبدیل شود.

---

# 38. GENERATION ENGINE

Generation Engine مسئول طراحی و تولید امضاهای جدید است.

Capabilityهای آن:

```text
Style Retrieval
Name Interpretation
Signature Planning
Stroke Design
Geometry Generation
Motion Synthesis
Controlled Variation
Candidate Generation
Candidate Evaluation
Rendering
PNG Export
Technical Artifact Creation
```

این موارد Engineهای مستقل نیستند.

---

# 39. CORE ↔ KNOWLEDGE ENGINE

قرارداد مفهومی:

```python
learn(sample)
analyze(sample)
update_knowledge(sample)
get_style_knowledge()
validate_sample(sample)
```

Knowledge Engine دانش را تحلیل و به‌روزرسانی می‌کند، اما مالک کل سیستم نیست.

---

# 40. CORE ↔ GENERATION ENGINE

قرارداد مفهومی:

```python
generate(
    name,
    knowledge,
    count=30,
)
```

Generation Engine:

1. Knowledge را دریافت می‌کند.
2. Candidate طراحی می‌کند.
3. Candidateها را ارزیابی می‌کند.
4. نتیجه را به Core برمی‌گرداند.

---

# 41. GENERATION MUST NOT BE RANDOM

Generation نباید به شکل زیر باشد:

```text
Knowledge
    ↓
Random Mutation
    ↓
Fake Signature
```

مدل موردنظر:

```text
Knowledge
    ↓
Style Constraints
    ↓
Structural Rules
    ↓
Stroke Grammar
    ↓
Motion Rules
    ↓
Controlled Variation
    ↓
New Signature
```

Candidate باید یک عضو طبیعی از فضای سبک آموخته‌شده باشد.

---

# 42. STYLE + MOTION RULE

Knowledge فقط Appearance نیست.

سیستم باید دو نوع دانش را یاد بگیرد:

## Style

```text
Shape
Proportion
Stroke Structure
Stroke Order
Composition
```

## Motion

```text
Velocity
Pressure
Direction
Curvature
Timing
Inter-stroke Gaps
```

Generation باید از هر دو استفاده کند.

---

# 43. GENERATION TARGET

هدف اولیه Generation:

```text
Reference Samples
        ↓
Knowledge 0.3
        ↓
Generation Engine
        ↓
3 Candidate Signatures
        ↓
Human / Visual / Structural Evaluation
```

در این مرحله نباید ادعا شود که سیستم با 25 Sample می‌تواند برای هر نامی تعداد زیادی Signature باکیفیت تولید کند.

هدف اولیه، **اثبات Generation واقعی و ارزیابی آن** است.

---

# 44. FUTURE GENERATION TARGET

پس از تثبیت Generation اولیه:

```text
Customer Name
      ↓
20–30 Candidates
      ↓
Style / Quality Scoring
      ↓
Ranking
      ↓
Top Candidates
      ↓
Human Approval
```

در مقیاس بزرگ‌تر هدف می‌تواند:

```text
30 Candidates
      ↓
Human Review
      ↓
5 Approved
      ↓
Knowledge Update
```

باشد.

---

# 45. HUMAN APPROVAL IS REQUIRED

Candidate تولیدشده نباید بدون کنترل وارد Knowledge شود.

مسیر صحیح:

```text
Generation
    ↓
Candidate
    ↓
Core
    ↓
Human Approval
    ↓
Validation
    ↓
Knowledge Engine
    ↓
Knowledge Update
```

Human Approval بخشی از حلقه یادگیری است.

---

# 46. GENERATED SAMPLE FEEDBACK

Sample تولیدشده فقط در صورتی می‌تواند وارد Knowledge شود که:

1. Candidate تولید شده باشد.
2. توسط Core مدیریت شود.
3. توسط انسان تأیید شود.
4. Validation انجام شود.
5. به Canonical Sample تبدیل شود.
6. سپس وارد Knowledge Engine شود.

Generation نباید مستقیماً Knowledge را تغییر دهد.

---

# 47. MANUAL SAMPLE FEEDBACK

نمونه‌ای که طراح پروژه به‌صورت دستی ایجاد و تأیید می‌کند نیز می‌تواند وارد چرخه Knowledge شود:

```text
Manual Design
    ↓
Validation
    ↓
Canonical Sample
    ↓
Knowledge Engine
    ↓
Updated Knowledge
```

در نتیجه Knowledge آینده می‌تواند شامل:

```text
Manual Samples
+
Approved Generated Samples
```

باشد.

---

# 48. CUMULATIVE LEARNING

Knowledge باید به‌صورت تدریجی و cumulative رشد کند.

مدل کلی:

```text
25
 ↓
100
 ↓
500
 ↓
1000+
```

با افزایش Sampleها انتظار می‌رود:

* تنوع Style افزایش یابد.
* فضای حرکتی بهتر شناخته شود.
* Generation بهتر شود.
* Candidateهای متنوع‌تر تولید شوند.

---

# 49. LONG-TERM DATASET TARGET

هدف بلندمدت Dataset:

```text
1000+ Reference Samples
```

است.

پس از رسیدن Knowledge به سطح مناسب، هدف Generation می‌تواند تولید:

```text
20–30 Candidates per Customer
```

باشد.

این یک هدف توسعه‌ای است، نه قابلیت تضمین‌شده فعلی.

---

# 50. CUSTOMER PACKAGE AS STANDARD OUTPUT

هر Sample تأییدشده باید در بلندمدت هم‌زمان:

```text
Reference Learning Sample
```

و:

```text
Complete Customer Package
```

باشد.

یعنی:

> هر Sample تأییدشده = Reference آموزشی معتبر + Package استاندارد

---

# 51. OPTIONAL FUTURE ARTIFACTS

در معماری آینده امکان وجود Artifactهای دیگر نیز در نظر گرفته شده است:

```text
PNG
Video
PDF Training File
Technical Data
Other Project Artifacts
```

جزئیات دقیق هر Artifact باید هنگام پیاده‌سازی همان بخش تثبیت شود.

نباید قبل از نیاز واقعی، فایل‌های اضافی ایجاد شوند.

---

# 52. DEVELOPMENT RULE: PRESERVE WORKING SYSTEM

Learning و Reference Knowledge سالم موجود نباید بدون دلیل بازنویسی یا تخریب شوند.

به‌خصوص:

```text
Knowledge 0.3
Reference Dataset
Existing Learning Pipeline
```

باید حفظ شوند.

هر توسعه جدید باید روی سیستم موجود ساخته شود، نه اینکه آن را بدون ضرورت از ابتدا بازنویسی کند.

---

# 53. NEW CAPABILITY DECISION RULE

قبل از ساخت هر فایل یا Component جدید، ابتدا سؤال زیر باید پاسخ داده شود:

```text
Does an existing component already own this responsibility?
```

سپس مشخص شود قابلیت متعلق به کدام بخش است:

### Management / Orchestration

```text
CORE
```

### Learning / Analysis / Recognition / Knowledge

```text
KNOWLEDGE ENGINE
```

### Design / Generation / Rendering

```text
GENERATION ENGINE
```

پیش‌فرض پروژه:

> فایل یا Engine جدید نساز؛ ابتدا از معماری موجود استفاده کن.

---

# 54. PIPELINE CURRENT STATE

Pipeline مرجع فعلی:

```text
Surface Pen
      ↓
Online Training
      ↓
Reference Samples
      ↓
Feature Extraction
      ↓
Reference Knowledge 0.3
      ↓
Generation Engine
      ↓
Candidates
      ↓
Human Approval
      ↓
Validation
      ↓
Knowledge Update
```

Generation در نقطه فعلی هنوز در حال توسعه است.

---

# 55. CURRENT COMPLETED COMPONENTS

موارد تأییدشده/انجام‌شده:

```text
[✓] Surface Pen Input
[✓] Online Drawing
[✓] Raw Stroke Capture
[✓] Pressure Capture
[✓] PNG Preservation
[✓] JSON Preservation
[✓] Metadata Preservation
[✓] Approved-only Saving
[✓] Unified Reference Dataset
[✓] 25 Reference Samples
[✓] Knowledge Schema 0.3
[✓] Sample Registration
[✓] Feature Extraction
[✓] Geometry Profiles
[✓] Velocity Profiles
[✓] Pressure Profiles
[✓] Direction Profiles
[✓] Curvature Profiles
[✓] Fixed Profile Resampling
[✓] Welford Aggregation
[✓] Successful Knowledge Rebuild
[✓] Reference Analysis
[✓] Labeled Samples
[✓] Unlabeled Samples
[✓] Persian / English / Mixed Labels
[✓] Customer Package Standards
```

---

# 56. CURRENTLY UNFINISHED

مواردی که هنوز باید توسعه داده شوند:

```text
[ ] Generation Engine
[ ] Style Retrieval for Generation
[ ] Signature Planning
[ ] New Trajectory Generation
[ ] Controlled Variation
[ ] Candidate Generation
[ ] Candidate Scoring
[ ] Candidate Ranking
[ ] PNG Rendering Pipeline for Generation
[ ] Generation Artifact Package
[ ] Human Approval Workflow
[ ] Approved-Sample Feedback
[ ] Advanced Incremental Learning
```

---

# 57. DEVELOPMENT ORDER

ترتیب توسعه تأییدشده:

```text
STEP 1
Reference Dataset
    ↓
Knowledge 0.3
    ✓ COMPLETED

STEP 2
Generation Engine
    ↓
Generate 3 Candidates
    ↓
Visual / Structural Evaluation

STEP 3
Improve Generation
    ↓
Controlled Variation
    ↓
Candidate Scoring

STEP 4
Generate 20–30 Candidates
    ↓
Human Approval

STEP 5
Approved Candidates
    ↓
Knowledge Engine
    ↓
Incremental Learning

STEP 6
Expand Dataset
    ↓
100 / 500 / 1000+

STEP 7
Advanced Generation
    ↓
20–30 Candidates per Customer
    ↓
Human Selection
    ↓
Continuous Knowledge Growth
```

---

# 58. CURRENT NEXT PRIORITY

طبق آخرین تصمیم ثبت‌شده، دو مسیر توسعه باید از هم تفکیک شوند:

### Pipeline / Package

استانداردهای Sample 025+ باید حفظ و به‌صورت خودکار تولید شوند.

### Rendering

بهینه‌سازی Smooth Rendering باید بدون تغییر در:

```text
Raw Data
PNG Standard
PDF Standard
Video Standard
Package Standard
```

انجام شود.

### Generation

پس از تثبیت Knowledge 0.3، گام اصلی معماری:

```text
Design & Implement Generation Engine
```

است.

---

# 59. GITHUB / VERSION CONTROL POLICY

کد پروژه باید Version Controlled باشد.

Knowledge Reference نیز در صورت تصمیم نهایی می‌تواند Version Controlled باشد.

اما:

```text
Code → version controlled
Reference Knowledge → version controlled
Private Customer Data → protected
```

داده خصوصی مشتری نباید بدون تصمیم امنیتی مناسب در Repository عمومی قرار گیرد.

Repository عمومی نباید محل انتشار ناخواسته داده‌های مرجع یا مشتری باشد.

---

# 60. VIRTUAL ENVIRONMENT POLICY

محیط Python پروژه:

```text
.venv
```

باید Local باشد.

`.venv` نباید به‌عنوان فایل پروژه وارد Git شود.

در دستگاه جدید، محیط Python باید در صورت نیاز دوباره ساخته شود.

---

# 61. ARCHITECTURAL ANTI-PATTERNS

موارد زیر در معماری پروژه ممنوع یا نامطلوب هستند:

### Parallel Engines

```text
geometry_engine
pressure_engine
velocity_engine
...
```

### Random Generation

```text
random mutation → fake signature
```

### Font-only Generation

```text
name → handwriting font → PNG
```

### Direct Knowledge Mutation

```text
Generation → Knowledge
```

بدون Human Approval و Validation.

### Raw Data Destruction

```text
Raw Stroke → Smooth → overwrite Raw
```

### Archive Rewriting

تغییر Sampleهای 001–024 برای اعمال Featureهای جدید.

### Unnecessary Reimplementation

بازنویسی Learning سالم بدون دلیل.

---

# 62. NON-NEGOTIABLE PROJECT RULES

قوانین زیر به‌عنوان قوانین اصلی پروژه ثبت می‌شوند:

## Rule 01

تمام Sampleهای تأییدشده بخشی از Reference Learning هستند.

## Rule 02

MASTER و APPROVED از نظر ارزش یادگیری تفاوت ندارند.

## Rule 03

`unlabeled` بودن Sample باعث حذف ارزش آموزشی آن نمی‌شود.

## Rule 04

Touch نباید صرفاً به دلیل وجودش حذف شود.

## Rule 05

Sample ردشده وارد Reference Dataset نمی‌شود.

## Rule 06

Raw Stroke Data باید حفظ شود.

## Rule 07

PNG و Metadata همراه Raw Data نگهداری می‌شوند.

## Rule 08

Analyzer و Feature Extractor نباید Dataset اصلی را تغییر دهند.

## Rule 09

قبل از ساخت فایل جدید، قابلیت‌های موجود بررسی شوند.

## Rule 10

از ساخت Engine و Fileهای موازی جلوگیری شود.

## Rule 11

Core مالک و Orchestrator اصلی سیستم است.

## Rule 12

پروژه حداکثر دو Main Engine دارد:

```text
Knowledge Engine
Generation Engine
```

## Rule 13

Visual Recognition متعلق به Knowledge Engine است.

## Rule 14

Learning و Analysis متعلق به Knowledge Engine هستند.

## Rule 15

Design و Generation متعلق به Generation Engine هستند.

## Rule 16

Generation نباید صرفاً Random یا Font-based باشد.

## Rule 17

Generation باید از Style و Motion Knowledge استفاده کند.

## Rule 18

Candidate تولیدشده قبل از ورود به Knowledge باید Human Approval و Validation دریافت کند.

## Rule 19

Knowledge باید cumulative و تدریجی رشد کند.

## Rule 20

Knowledge سالم موجود نباید بدون دلیل بازنویسی یا تخریب شود.

## Rule 21

Sampleهای 001–024 آرشیو تثبیت‌شده هستند.

## Rule 22

Sampleهای 025+ باید تمام استانداردهای 001–024 را به ارث ببرند.

## Rule 23

هر Save موفق Sample جدید باید یک Package کامل ایجاد کند.

## Rule 24

Sample ID باید یکتا باشد.

## Rule 25

Raw Data و Render دو لایه متفاوت هستند.

## Rule 26

Smooth فقط روی Render/Display اعمال می‌شود.

## Rule 27

PNG استاندارد خروجی Sample برابر `2400 × 1359` است.

## Rule 28

Video استاندارد برابر `1336 × 512 @ 60 FPS` است.

## Rule 29

Practice PDF استاندارد A4 با 20 Sample و Layout چهار ستون × پنج ردیف است.

## Rule 30

فایل‌های جدید باید با معماری `Core + Knowledge Engine + Generation Engine` سازگار باشند.

---

# 63. MASTER ARCHITECTURE

معماری نهایی مرجع:

```text
                         SIGNATURE MACHINE
                                |
                                v
                              CORE
                             OWNER
                                |
                +---------------+---------------+
                |                               |
                v                               v
        KNOWLEDGE ENGINE                GENERATION ENGINE
                |                               |
        +-------+--------+              +-------+--------+
        |       |        |              |       |        |
      Learn   Analyze  Validate       Design  Generate  Render
        |       |        |              |       |        |
        +-------+--------+              +-------+--------+
                |                               |
                +---------------+---------------+
                                |
                                v
                         CANDIDATE OUTPUT
                                |
                                v
                         HUMAN APPROVAL
                                |
                                v
                           CORE VALIDATION
                                |
                                v
                        KNOWLEDGE ENGINE
                                |
                                v
                         KNOWLEDGE UPDATE
```

---

# 64. FINAL PROJECT PRINCIPLE

Signature Machine نباید به یک سیستم تقلید تصویر تبدیل شود.

هدف اصلی:

```text
Learn Style
+
Learn Structure
+
Learn Motion
+
Learn Stroke Grammar
+
Learn Design Rules
        ↓
Controlled Generation
        ↓
New Signature
        ↓
Human Approval
        ↓
Knowledge Growth
        ↓
Better Generation
```

است.

---

# 65. FINAL REFERENCE STATE

وضعیت مرجع فعلی:

```text
REFERENCE DATASET
        ↓
25 VALIDATED SAMPLES
        ↓
KNOWLEDGE 0.3
        ↓
STYLE + STRUCTURE + MOTION KNOWLEDGE
        ↓
READY FOR GENERATION ENGINE
```

Generation Engine هنوز در حال توسعه است.

هدف مرحله فعلی، ساخت **یک Generation Engine اصلی، بدون همپوشانی و بر پایه Knowledge 0.3** است.

---

# 66. FINAL LOCK

از این پس هر تصمیم توسعه‌ای جدید باید با این سند بررسی شود.

اگر تصمیم جدیدی با یکی از قوانین این سند تعارض داشته باشد، نباید صرفاً با تغییر کد اعمال شود.

ابتدا باید:

1. تعارض شناسایی شود.
2. دلیل تغییر مشخص شود.
3. تصمیم جدید به‌صورت صریح تأیید شود.
4. نسخه این سند به‌روزرسانی شود.
5. سپس تغییر در کد یا Dataset اعمال شود.

اصل نهایی:

> **CODE MUST FOLLOW THE CONFIRMED ARCHITECTURE.**

و:

> **DATA MUST NOT BE CHANGED JUST BECAUSE THE IMPLEMENTATION CHANGED.**

و:

> **ONE CORE + TWO MAIN ENGINES + ONE UNIFIED REFERENCE KNOWLEDGE.**

---

# END OF MASTER PROJECT RULES
