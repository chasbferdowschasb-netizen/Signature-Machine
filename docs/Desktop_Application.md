# SIGNATURE MACHINE

## سند معماری نرم‌افزار Desktop، Workspace قابل‌حمل و امنیت داده

**Document Type:** Software Architecture & Operational Specification
**Project:** Signature Machine
**Version:** v0.1
**Status:** Architecture Decision / Development Specification
**Date:** 2026-08-24

---

# 1. هدف سند

این سند معماری موردنظر برای تبدیل Signature Machine به یک نرم‌افزار اختصاصی Desktop را تعریف می‌کند.

Signature Machine یک محصول عمومی برای انتشار یا فروش نیست؛ این سیستم به‌صورت اختصاصی برای استفاده شخصی و ارتقای فرآیند کسب‌وکار مالک پروژه طراحی می‌شود.

هدف این معماری آن است که:

* نرم‌افزار به‌صورت Windows Desktop و قابل نصب اجرا شود.
* فایل Installer داخل Master USB پروژه وجود داشته باشد.
* نرم‌افزار روی هر سیستم Windows قابل نصب باشد، بدون وابستگی دائمی به یک کامپیوتر خاص.
* تمام دانش، Sampleها، Modelها و Assetهای پروژه در یک Workspace اصلی قابل‌حمل نگهداری شوند.
* Master USB علاوه بر نقش Storage، نقش Hardware Authorization Key را نیز داشته باشد.
* Sampleهای جدید مستقیماً از طریق نرم‌افزار روی Master USB ذخیره شوند.
* Database و Knowledge بین سیستم‌های مختلف به‌صورت خودکار یکسان باقی بمانند.
* پروژه به یک هارد یا لپ‌تاپ خاص وابسته نباشد.
* در صورت خرابی یا گم‌شدن Master USB، امکان بازیابی پروژه و ساخت Master USB جدید وجود داشته باشد.
* Backup رمزگذاری‌شده روی سیستم محلی ایجاد شود.
* بدون Authorization Code و Recovery Code، شخص دیگر نتواند پروژه را روی سیستم یا USB دیگری فعال کند.
* فایل‌های اصلی پروژه به‌صورت قابل‌خواندن و بدون محافظت روی USB قرار نگیرند.

---

# 2. اصل معماری اصلی

اصل اصلی این سیستم:

> **Application مستقل از Project Data است، اما Project Data به‌صورت یک Workspace رمزگذاری‌شده و قابل‌حمل در Master USB نگهداری می‌شود.**

معماری کلی:

```text
SignatureMachine.exe
        │
        │
        ▼
Application / Engine / UI
        │
        │
        ▼
Master USB
        │
        ├── Installer
        ├── Application Components
        ├── Hardware Identity
        └── Encrypted Workspace
                │
                ├── Database
                ├── Knowledge
                ├── Models
                ├── Samples
                ├── PNG / SVG
                ├── PDF
                ├── Videos
                ├── Evaluations
                └── Project History
```

Master USB منبع اصلی Workspace پروژه است.

---

# 3. ساختار سه‌لایه سیستم

سیستم از سه بخش اصلی تشکیل می‌شود:

## 3.1 Application Layer

شامل:

* Desktop UI
* Design Canvas
* Sample Manager
* Knowledge Manager
* Model Manager
* Training Manager
* Evaluation Manager
* Backup Manager
* Recovery Manager
* Security / Authorization Manager

Application روی Windows نصب می‌شود.

---

## 3.2 Workspace Layer

Workspace شامل تمام اطلاعات واقعی پروژه است:

* Database
* Samples
* Knowledge
* Models
* Generated Outputs
* Evaluations
* Training Data
* Documentation
* Videos
* PDFs
* Images
* Project History

Workspace باید از Application مستقل باشد.

---

## 3.3 Security Layer

وظیفه Security Layer:

* تشخیص Master USB
* بررسی Hardware Identity
* Authorization
* Activation
* Backup Encryption
* Workspace Encryption
* Recovery
* Revocation
* ایجاد Master USB جدید

---

# 4. Master USB

Master USB مرجع اصلی پروژه است.

Master USB فقط یک فلش برای انتقال فایل نیست؛ بلکه سه نقش دارد:

1. **Project Storage**
2. **Hardware Authorization Key**
3. **Portable Workspace**

ساختار منطقی:

```text
MASTER USB
│
├── INSTALLER
│
├── APPLICATION
│
├── HARDWARE IDENTITY
│
└── ENCRYPTED WORKSPACE
```

اطلاعات حساس باید در Workspace رمزگذاری‌شده قرار بگیرند.

---

# 5. Installer

Installer باید داخل Master USB قرار داشته باشد.

نمونه:

```text
SignatureMachine_Setup.exe
```

هدف این است که برای نصب Signature Machine نیازی به دانلود نرم‌افزار از اینترنت یا منبع خارجی نباشد.

کاربر:

```text
USB
  ↓
Run Installer
  ↓
Installation
  ↓
Master USB Detection
  ↓
Authorization Code
  ↓
Activation
  ↓
Desktop Environment
```

### محدودیت Windows

اجرای خودکار Installer صرفاً با اتصال USB نباید به‌عنوان الزام معماری در نظر گرفته شود، زیرا Windows اجرای خودکار برنامه از USB را محدود می‌کند.

بنابراین USB باید Installer را در اختیار داشته باشد و کاربر آن را اجرا کند.

---

# 6. نصب روی سیستم جدید

سناریوی نصب:

```text
1. Master USB وصل می‌شود.
2. Installer اجرا می‌شود.
3. Signature Machine نصب می‌شود.
4. Master USB شناسایی می‌شود.
5. Hardware Identity بررسی می‌شود.
6. Authorization Code درخواست می‌شود.
7. در صورت موفقیت، Workspace قابل استفاده می‌شود.
8. محیط Desktop باز می‌شود.
```

بدون Authorization معتبر، فعال‌سازی کامل انجام نمی‌شود.

---

# 7. وابستگی نرم‌افزار به هارد سیستم

Signature Machine نباید به یک هارد یا لپ‌تاپ خاص وابسته باشد.

این موارد نباید مرجع اصلی پروژه باشند:

```text
C:\SignatureMachine\Data
```

یا:

```text
D:\SignatureMachine\
```

مرجع اصلی باید Master USB باشد.

بنابراین:

```text
Laptop A
+
Master USB
=
Signature Machine Workspace


Laptop B
+
Master USB
=
همان Workspace
```

---

# 8. Database

Database مرجع مدیریتی پروژه است.

Database باید اطلاعاتی مانند موارد زیر را نگهداری کند:

* Sample ID
* Sample Version
* Status
* Creation Date
* Source
* Generation Parameters
* Evaluation Results
* Model Version
* Knowledge Version
* Training Status
* File References
* Workspace Version
* Project History

Database داخل Workspace رمزگذاری‌شده قرار می‌گیرد.

---

# 9. ساختار Sample

هر Sample باید یک ساختار مستقل داشته باشد.

مثال:

```text
SAMPLES/
└── 025/
    ├── SOURCE/
    ├── PNG/
    ├── SVG/
    ├── VIDEO/
    ├── PDF/
    ├── EVALUATION/
    ├── METADATA/
    └── SAMPLE MANIFEST
```

فایل‌های Sample نباید صرفاً به‌صورت فایل‌های پراکنده ذخیره شوند.

هر Sample باید دارای Metadata و شناسه یکتا باشد.

---

# 10. ذخیره PNG، SVG، PDF و Video

خروجی‌های تولیدشده برای هر Sample باید در Workspace ذخیره شوند.

نمونه:

```text
Sample 025
│
├── PNG
│   ├── final.png
│   └── preview.png
│
├── SVG
│   └── final.svg
│
├── PDF
│   └── documentation.pdf
│
└── VIDEO
    └── training.mp4
```

Database مسیر منطقی فایل‌ها و مشخصات آنها را ثبت می‌کند.

---

# 11. Knowledge

Knowledge باید در دو سطح نگهداری شود.

## 11.1 Human Knowledge

اطلاعات قابل مطالعه برای انسان:

```text
Knowledge/
├── Rules/
├── Architecture/
├── Decisions/
├── Documentation/
└── Manuals/
```

فرمت‌هایی مانند:

* Markdown
* PDF
* Documentation

می‌توانند در این بخش قرار بگیرند.

## 11.2 Machine Knowledge

اطلاعات قابل استفاده مستقیم توسط Engine:

```text
Knowledge/
└── Machine/
    ├── style_parameters
    ├── motion_rules
    ├── learned_features
    └── model_configuration
```

Machine Knowledge نباید صرفاً به PDF یا متن انسانی وابسته باشد.

---

# 12. Model

Model آموزش‌دیده باید از Dataset خام مستقل باشد.

هدف:

```text
Model
+
Machine Knowledge
+
Engine
=
Generate
```

نه:

```text
Model
+
اجبار به دسترسی دائمی به Sampleهای خام
=
Generate
```

بنابراین پس از آموزش موفق، Model باید بتواند در Runtime بدون نیاز به تمام Sampleهای خام، خروجی جدید تولید کند.

---

# 13. Dataset و Sampleها

Dataset اصلی همچنان باید حفظ شود.

Sampleها برای موارد زیر ضروری هستند:

* Training
* Fine-tuning
* Evaluation
* Comparison
* Model Validation
* Knowledge Reconstruction
* Research
* Audit
* Future Development

بنابراین حذف Sampleهای اصلی پس از آموزش ممنوع است، مگر با تصمیم صریح مالک پروژه.

---

# 14. ورود Sample جدید

تمام Sampleهای جدید باید از طریق Application مدیریت شوند.

Workflow:

```text
New Sample
    ↓
Input / Recording
    ↓
Processing
    ↓
Generation
    ↓
Evaluation
    ↓
Approval
    ↓
Database Commit
    ↓
Write to Master USB
    ↓
Backup Update
```

Application نباید فقط خروجی را روی Desktop یا Downloads ذخیره کند و آن را خارج از Database رها کند.

---

# 15. اصل Write Through Application

تمام تغییرات اصلی Workspace باید از طریق خود نرم‌افزار انجام شوند.

به‌صورت معمول کاربر نباید فایل‌های داخلی Workspace را دستی ویرایش کند.

مثال:

```text
User
 ↓
Signature Machine UI
 ↓
Create Sample
 ↓
Save
 ↓
Database
 ↓
Workspace
 ↓
Backup
```

این موضوع برای جلوگیری از خراب‌شدن ساختار Database و Metadata ضروری است.

---

# 16. Backup

Master USB نباید تنها محل نگهداری پروژه باشد.

Application باید یک Backup رمزگذاری‌شده روی سیستم محلی ایجاد کند.

مثال:

```text
Signature Machine Backup/
└── SignatureMachine_Backup.smbak
```

Backup می‌تواند شامل موارد زیر باشد:

* Database
* Knowledge
* Models
* Samples
* Generated Files
* Evaluations
* Documentation
* Videos
* PDFs
* Project History

---

# 17. Backup دو سطحی

سیستم باید در طراحی امکان دو نوع Backup را داشته باشد.

## Full Backup

شامل کل پروژه:

```text
Model
Knowledge
Database
Samples
PNG
SVG
PDF
Video
Evaluation
History
```

## Model/Operational Backup

شامل اجزای مورد نیاز برای اجرای سریع:

```text
Model
Machine Knowledge
Required Configuration
Database Metadata
```

Full Backup مرجع اصلی بازیابی پروژه است.

---

# 18. Backup Encryption

Backup نباید به‌صورت فایل‌های عادی و قابل‌خواندن ذخیره شود.

مثلاً:

```text
SignatureMachine_Backup.smbak
```

باید یک Container رمزگذاری‌شده باشد.

هدف:

اگر فایل Backup توسط شخص دیگری کپی شود، بدون کلیدهای معتبر نتواند:

* Sampleها را استخراج کند.
* Knowledge را بخواند.
* Model را استفاده کند.
* Videos را مشاهده کند.
* Database را باز کند.

---

# 19. Activation Code

Activation Code برای فعال‌سازی نرم‌افزار روی سیستم جدید استفاده می‌شود.

فرآیند:

```text
Installer
   ↓
Master USB Detected
   ↓
Activation Code
   ↓
Validation
   ↓
Activate
```

بدون کد معتبر، فعال‌سازی انجام نمی‌شود.

---

# 20. تفکیک کلیدهای امنیتی

نباید یک رمز واحد برای تمام عملیات استفاده شود.

حداقل سه مفهوم امنیتی باید مستقل باشند:

```text
Activation Code
        ≠
Backup Encryption Key
        ≠
Recovery Authorization
```

هدف این است که افشای یک Credential باعث از بین رفتن تمام لایه‌های امنیتی نشود.

---

# 21. Hardware Identity

Master USB باید دارای یک Identity اختصاصی باشد.

به‌صورت مفهومی:

```text
MASTER_USB_ID
+
Cryptographic Identity
+
Workspace Identity
```

Application باید هنگام اتصال USB، هویت آن را بررسی کند.

صرفاً کپی کردن فایل‌های Workspace روی یک USB دیگر نباید برای ساخت Master USB معتبر کافی باشد.

---

# 22. جلوگیری از کپی ساده Workspace

اگر شخصی محتویات USB را روی فلش دیگری کپی کند:

```text
Copied USB
   ↓
No Valid Hardware Identity
   ↓
Invalid Master
```

بنابراین:

> Workspace قابل کپی فایل‌به‌فایل نباید به‌تنهایی برای فعال‌سازی پروژه کافی باشد.

---

# 23. Recovery

در صورت گم‌شدن یا خرابی Master USB باید امکان Recovery وجود داشته باشد.

سناریو:

```text
Master USB Lost
       ↓
New USB
       ↓
Install Signature Machine
       ↓
Restore from Encrypted Backup
       ↓
Recovery Authorization
       ↓
Create New Master Identity
       ↓
Write Workspace
       ↓
Register New Master USB
```

---

# 24. Revocation

پس از گم‌شدن Master USB، امکان ثبت USB قبلی به‌عنوان:

```text
REVOKED
```

باید وجود داشته باشد.

هدف:

اگر USB گم‌شده بعداً پیدا شد، نتواند بدون Authorization دوباره به‌عنوان Master معتبر استفاده شود.

---

# 25. Recovery Code

Recovery Code باید فقط برای مالک پروژه در دسترس باشد.

Recovery Code نباید روی خود Master USB ذخیره شود.

در صورت گم‌شدن USB:

```text
Backup
+
Recovery Authorization
+
New USB
```

برای ایجاد Master جدید استفاده می‌شود.

---

# 26. انتقال به لپ‌تاپ جدید

سناریوی عادی:

```text
Laptop New
      ↓
Install Signature Machine
      ↓
Connect Master USB
      ↓
Authorization
      ↓
Workspace Detected
      ↓
Database Loaded
      ↓
Knowledge Loaded
      ↓
Model Loaded
      ↓
Design Environment Ready
```

هیچ Migration دستی Sampleها لازم نیست.

---

# 27. تغییرات بین سیستم‌ها

هر Sample جدید یا هر تغییر تأییدشده باید مستقیماً در Master Workspace ثبت شود.

مثال:

```text
Laptop A
   ↓
Sample 026
   ↓
Master USB
```

سپس:

```text
Master USB
   ↓
Laptop B
   ↓
Sample 026 Available
```

بنابراین Master USB مرجع اصلی Database باقی می‌ماند.

---

# 28. Offline-First

Signature Machine نباید برای عملکرد اصلی خود به اینترنت وابسته باشد.

هدف:

```text
Master USB
+
Windows
+
Signature Machine
=
Complete Working Environment
```

این معماری برای استفاده اختصاصی و قابل‌حمل پروژه در نظر گرفته می‌شود.

---

# 29. اینترنت

در معماری فعلی، اینترنت برای موارد زیر الزامی نیست:

* اجرای نرم‌افزار
* مشاهده Sampleها
* تولید Signature
* دسترسی به Knowledge
* استفاده از Model
* ذخیره Sample
* مشاهده ویدئوها
* مشاهده PDFها

در صورت نیاز آینده، قابلیت‌های Online باید به‌عنوان لایه جداگانه اضافه شوند و وابستگی Runtime ایجاد نکنند.

---

# 30. Design Environment

Desktop Application باید محیط طراحی مستقل داشته باشد.

اجزای اصلی:

```text
┌──────────────────────────────────────────┐
│ Signature Machine                        │
├────────────┬─────────────────────────────┤
│ Knowledge  │                             │
│ Samples    │        DESIGN CANVAS        │
│ Design     │                             │
│ Training   │                             │
│ Evaluation │                             │
│ Models     │                             │
│ Backup     │                             │
│ Settings   │                             │
├────────────┴─────────────────────────────┤
│ Generate | Save | Evaluate | Export       │
└──────────────────────────────────────────┘
```

---

# 31. Sample Browser

Application باید امکان مشاهده و مدیریت Sampleها را فراهم کند.

مثال:

```text
001   Approved
002   Approved
003   Approved
...
024   Reference
025   Approved
026   Approved
...
```

با انتخاب Sample، موارد زیر قابل مشاهده باشند:

* Preview
* PNG
* SVG
* Video
* PDF
* Metadata
* Evaluation
* Model Version
* Knowledge Version

---

# 32. Versioning

Model، Knowledge، Database و Sampleها باید دارای Version یا Revision قابل ردیابی باشند.

مثال:

```text
Model v01
Model v02
Model v03
```

و:

```text
Knowledge v01
Knowledge v02
```

هر Sample باید مشخص کند با چه Versionهایی مرتبط بوده است.

---

# 33. Integrity

Workspace باید دارای Integrity Check باشد.

Application باید بتواند تشخیص دهد:

* Database خراب شده است.
* فایل Sample ناقص است.
* فایل تغییر کرده است.
* Workspace متعلق به Master USB نیست.
* Backup معتبر نیست.
* Model ناقص است.

برای این منظور استفاده از Hash و Manifest در معماری توصیه می‌شود.

---

# 34. Workspace Manifest

Workspace باید دارای Manifest باشد.

مثال مفهومی:

```text
Workspace ID
Master ID
Workspace Version
Database Version
Knowledge Version
Model Version
Sample Count
Last Update
Integrity Status
```

Manifest برای تشخیص صحت Workspace استفاده می‌شود.

---

# 35. اصل استقلال Model از Dataset خام

هدف نهایی این است که Model آموزش‌دیده بتواند بدون وابستگی Runtime به تمام Sampleهای خام کار کند.

بنابراین:

```text
Engine
+
Model
+
Machine Knowledge
```

باید برای Generation کافی باشد.

اما Dataset اصلی باید برای:

```text
Retraining
Fine-tuning
Validation
Research
Reconstruction
```

حفظ شود.

---

# 36. ساختار منطقی نهایی Workspace

ساختار پیشنهادی:

```text
SM_WORKSPACE/
│
├── SYSTEM/
│   ├── workspace.id
│   ├── manifest
│   ├── version
│   └── integrity
│
├── DATABASE/
│   └── project database
│
├── KNOWLEDGE/
│   ├── HUMAN/
│   └── MACHINE/
│
├── MODELS/
│   ├── ACTIVE/
│   ├── PREVIOUS/
│   └── ARCHIVE/
│
├── SAMPLES/
│   ├── 001/
│   ├── 002/
│   ├── ...
│   └── 025/
│
├── TRAINING/
│
├── GENERATED/
│
├── EVALUATION/
│
├── DOCUMENTATION/
│
└── ARCHIVE/
```

این Workspace در لایه ذخیره‌سازی باید رمزگذاری شود.

---

# 37. رابطه EXE و Workspace

اصل معماری:

```text
EXE ≠ Workspace
```

EXE شامل:

* Application
* Engine
* UI
* Security
* Database Manager
* Workspace Manager

است.

Workspace شامل:

* Project Data
* Samples
* Knowledge
* Models
* Assets
* History

است.

---

# 38. دلیل این تفکیک

در صورت:

* تعویض لپ‌تاپ
* نصب مجدد Windows
* نصب نسخه جدید Signature Machine
* خرابی هارد
* انتقال پروژه
* Recovery

داده‌های پروژه نباید از بین بروند.

بنابراین:

```text
Application can change.
Computer can change.
Operating System can change.

Project Workspace remains.
```

---

# 39. سناریوی تعویض نسخه نرم‌افزار

مثلاً:

```text
Signature Machine v1
       ↓
Master USB
       ↓
Install v2
       ↓
Load existing Workspace
       ↓
Database Migration if required
       ↓
Continue Project
```

نسخه جدید نباید به‌صورت پیش‌فرض Dataset قبلی را حذف کند.

---

# 40. سناریوی گم‌شدن Laptop

اگر Laptop از بین برود:

```text
New Laptop
+
SignatureMachine.exe
+
Master USB
```

برای ادامه پروژه کافی است.

Backup محلی نیز به‌عنوان لایه دوم Recovery باقی می‌ماند.

---

# 41. سناریوی گم‌شدن Master USB

اگر Master USB گم شود:

```text
Encrypted Backup
+
Recovery Authorization
+
New USB
```

برای ایجاد Master USB جدید استفاده می‌شود.

USB قبلی باید در صورت امکان Revoked شود.

---

# 42. سناریوی از بین رفتن هم Laptop و هم USB

این حالت فقط در صورتی قابل Recovery است که Full Backup در محل دیگری موجود باشد.

بنابراین نگهداری حداقل یک Backup مستقل و امن خارج از Laptop ضروری است.

---

# 43. اصل مهم Backup

> **Master USB مرجع عملیاتی است؛ Backup مرجع بازیابی است.**

هیچ‌کدام نباید تنها نسخه پروژه باشند.

---

# 44. امنیت فایل‌های شخصی پروژه

از آنجا که Signature Machine یک سیستم اختصاصی و خصوصی است، تمام موارد زیر باید به‌عنوان داده حساس پروژه در نظر گرفته شوند:

* Samples
* Original Recordings
* Videos
* PDFs
* Knowledge
* Models
* Training Data
* Evaluation Data
* Database
* Project History

این داده‌ها نباید در Installer عمومی یا فایل‌های قابل‌دسترسی بدون Authorization قرار گیرند.

---

# 45. عدم انتشار عمومی

Signature Machine برای انتشار عمومی طراحی نمی‌شود.

هدف:

```text
Private Business Infrastructure
```

است.

بنابراین معماری می‌تواند حول نیازهای یک مالک و یک Workspace اصلی بهینه شود، نه مدیریت هزاران کاربر.

---

# 46. اولویت امنیت

ترتیب امنیتی پیشنهادی:

```text
Hardware Identity
        +
Authorization
        +
Workspace Encryption
        +
Backup Encryption
        +
Recovery Authorization
        +
Integrity Verification
```

---

# 47. تصمیم معماری برای Sampleهای آینده

از زمان شروع Desktop Architecture، Sampleهای جدید باید مستقیماً تحت مدیریت Workspace قرار بگیرند.

مجموعه Sampleهای مرجع قبلی باید حفظ شود.

در پروژه فعلی:

```text
001–024
    ↓
Reference Dataset
    ↓
Import / Register
    ↓
Desktop Workspace
    ↓
025+
    ↓
Managed by Signature Machine
```

Sampleهای مرجع نباید بازسازی یا تغییر داده شوند مگر طبق تصمیم صریح پروژه.

---

# 48. اصل جلوگیری از وابستگی به یک دستگاه

Signature Machine نباید به این موارد وابسته باشد:

* Serial Number یک Laptop
* هارد مشخص
* Windows Installation مشخص
* مسیر ثابت روی C:
* User Account مشخص

مرجع هویت پروژه:

```text
Master USB
+
Workspace Identity
+
Cryptographic Authorization
```

است.

---

# 49. اصل مالکیت پروژه

مالک پروژه باید تنها شخصی باشد که:

* Authorization Code
* Recovery Authorization
* Backup Encryption Access
* Master USB

را در اختیار دارد.

این موارد نباید در فایل‌های عمومی پروژه ذخیره شوند.

---

# 50. وضعیت نهایی مورد انتظار

معماری نهایی باید به این تجربه عملی برسد:

```text
مالک پروژه
     │
     ▼
Master USB
     │
     ▼
هر Windows Computer
     │
     ▼
Install / Activate
     │
     ▼
Signature Machine Desktop
     │
     ▼
Load Master Workspace
     │
     ├── Knowledge
     ├── Samples
     ├── Models
     ├── Database
     ├── Videos
     ├── PDFs
     ├── PNG / SVG
     └── History
     │
     ▼
Design / Generate / Evaluate / Train
     │
     ▼
Write Changes to Master USB
     │
     ▼
Update Encrypted Backup
```

---

# 51. اصل طلایی معماری

> **کامپیوتر محل اجرای Signature Machine است؛ Master USB محل هویت و Workspace پروژه است؛ Backup محل بازیابی پروژه است.**

در نتیجه:

```text
Computer = Replaceable
Application = Replaceable
Master USB = Portable Project Identity
Workspace = Project State
Backup = Recovery
Model = Learned Capability
Knowledge = Learned Rules
Dataset = Training Memory
```

---

# 52. تصمیم نهایی معماری

این معماری از این مرحله به بعد به‌عنوان Architecture Decision پروژه ثبت می‌شود:

1. Signature Machine به‌صورت Desktop Application توسعه خواهد یافت.
2. Installer داخل Master USB قرار خواهد داشت.
3. نصب نرم‌افزار به اینترنت وابسته نخواهد بود.
4. Master USB مرجع اصلی Workspace پروژه خواهد بود.
5. Workspace شامل Database، Knowledge، Models، Samples و تمام Assetهای پروژه خواهد بود.
6. Workspace باید محافظت و رمزگذاری شود.
7. Master USB علاوه بر Storage نقش Hardware Authorization Key خواهد داشت.
8. Sampleهای جدید از طریق خود نرم‌افزار روی Master Workspace ذخیره خواهند شد.
9. Database مرجع اصلی وضعیت پروژه خواهد بود.
10. Model آموزش‌دیده نباید برای Generation معمول به Dataset خام وابسته باشد.
11. Backup رمزگذاری‌شده باید به‌صورت مستقل از Master USB وجود داشته باشد.
12. Recovery امکان ساخت Master USB جدید را فراهم خواهد کرد.
13. Activation، Backup Encryption و Recovery Authorization باید از یکدیگر مستقل باشند.
14. USB گم‌شده باید قابلیت Revocation داشته باشد.
15. پروژه نباید به یک Laptop یا Hard Drive خاص وابسته باشد.
16. نصب نرم‌افزار به‌تنهایی نباید به معنی دسترسی به Dataset و Knowledge پروژه باشد.
17. فایل‌های حساس پروژه نباید به‌صورت Unencrypted روی USB ذخیره شوند.
18. Workspace باید دارای Manifest و Integrity Verification باشد.
19. تغییرات اصلی Workspace باید از طریق Application انجام شوند.
20. Architecture باید از Sample 025 به بعد مبنای مدیریت Sampleهای جدید باشد.

---

# 53. وضعیت این سند

**Status: APPROVED ARCHITECTURAL DIRECTION**

این سند مبنای طراحی Desktop Application و Data Architecture نسخه‌های بعدی Signature Machine است.

هرگونه تغییر در موارد زیر باید به‌عنوان Architecture Change ثبت شود:

* محل Master Workspace
* روش Hardware Authentication
* ساختار Database
* ساختار Sample
* روش Backup
* روش Recovery
* روش Encryption
* وابستگی Model به Dataset
* روش انتقال Workspace
* روش Authorization

**پایان سند**
