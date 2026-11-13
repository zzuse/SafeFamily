# Lotto ticket counter: the full plan

Goal: photograph the scratch-ticket display and get **how many tickets of
each value** are on it. Values are the same as in the Store Accounting tool:
$1, $2, $3, $4, $5, $7, $10, $20, $30, $50, $100.

Every ticket shows its price in its **top-left corner** ("$5" with the game
number under it). Tickets are fanned out and overlap, but each one keeps its
corner visible. So **counting tickets = counting price corners**, split by the
value printed in each corner.

Everything except training happens on the website (`/lotto`, the **Lotto**
tab). Training happens on the Mac, because the Linux server has no GPU. You
move one zip file to the Mac and one JSON file back.

```
 phone / browser            SafeFamily server (no GPU)                Mac (Apple GPU)
 ───────────────            ──────────────────────────                ───────────────
 1. take photo ──upload──▶ stores original untouched
    (any time)             "To label" backlog, no deadline
                           2. label: tap a box on every price corner,
                              pick its value; live tally per value
                           ⬇ export.zip (photos + manifest.jsonl) ──▶ 3a prepare_dataset.py
                                                                      3b baseline_ocr.py --count
                                                                      3c train_detector.py (finds corners)
                                                                      3d train_crnn.py     (reads values)
                           ⬆ predictions.json ◀────────────────────── 4  predict.py
                           unlabeled photos arrive pre-boxed;
                           labeled photos show "Model: N" vs yours
```

## The model: two small models, one job each

1. **Corner detector** (YOLO, fine-tuned). It finds every price corner in the
   photo and doesn't care about the value. It learns from *every* corner, about
   60 per tray photo, so it gets good quickly even on overlapping, tilted or
   glary corners.
2. **Value reader** (small CRNN). It reads the digits in each corner crop:
   "1", "2", … "100". It learns **digits**, not whole values, so a rare $50
   borrows its "5" and "0" from the common $5 and $10 tickets. Digits that
   appear in only one or two values (the "4" of $4, the "7" of $7) need
   enough examples of their own, which the $3/$4 and $1/$2/$7 trays provide.
   A new price needs no new detector.

Counts per value are a simple tally of the reader's answers.

**Train on mixed photos, exactly like the ones you'll use.** Don't take
separate photos of only $20 tickets. The model must learn to tell a $5 from a
$50 side by side, and to ignore prize text like "$100,000".

## Upload now, label later

You don't have to label on the day you take a photo:

* Every upload lands in **To label**. **Label next** opens the oldest waiting
  photo, so you can work through a backlog of weeks in one sitting.
* **Save** keeps a half-done photo as a draft ("draft · 37 boxes" on its
  card). Finish it another day.
* Photos are kept at full resolution forever. Nothing expires.
* The progress panel shows how many photos are waiting. For each milestone it
  shows "label N waiting photo(s) + ~D days of new photos", so you see whether
  you are short of photos or short of labeling time.
* Once you have a model, upload its predictions (step 4). Every waiting photo
  then arrives pre-boxed, and catching up on the backlog becomes checking.

Storage: phone photos are 3–6 MB, so 2 a day is about 300 MB a month in
Postgres, which is fine. Delete useless photos with **Delete**. **Skip**
keeps a photo but leaves it out of training.

## Step 0: one-time setup

Server (after pulling this change):

```bash
docker-compose up -d --build app
docker compose exec app python scripts/migrate.py   # creates/updates the lotto_photos table
```

Mac (Apple silicon, Python 3.11+):

```bash
git clone <this repo> && cd SafeFamily        # or just copy scripts/lotto/
python3 -m venv ~/lotto-venv && source ~/lotto-venv/bin/activate
pip install torch torchvision pillow ultralytics
pip install ocrmac                            # optional: Apple Live Text for the baseline check
python -c "import torch; print(torch.backends.mps.is_available())"   # should print True
```

## Step 1: take photos (about 1 minute)

Open `/lotto` on your phone, tap **Choose / take photos**, then **Upload**.

* **One photo per tray, not the whole case.** A full-case photo holds ~250
  tickets, and each price corner comes out only ~25 px tall, too small to label
  comfortably and too small for the detector once it scales the photo down. A
  tray photo makes every corner ~2.5× bigger. Trays are physically separate,
  so nothing is counted twice: the case total is the sum of the 4 tray photos.
* Shoot from **straight above**, the tray filling the frame, at full phone
  resolution. Don't crop or shrink it. Get closer rather than using digital
  zoom.
* The ceiling lights make round white reflections on the glass. Tilt the phone
  a little so they don't sit on a row of price corners. A little glare is OK:
  real photos have it, so the model must learn it.
* **Crop before upload.** A tray photo usually catches the edge of the
  neighbouring trays, and their tickets must not be counted twice. After you
  choose photos, each one shows a preview: drag a frame around the tray, drag
  inside the frame to move it, drag a corner to resize, or press **Use whole
  photo** to undo. Only the framed part is uploaded, cut from the
  full-resolution photo, so the price corners stay as sharp as in the original.
  Photos you don't frame are uploaded untouched.
* **HEIC (iPhone's default format) is converted to JPEG in the browser**
  before upload, because the training scripts can't read HEIC. iPhone Safari
  usually sends JPEG anyway. A browser that can't decode HEIC (e.g. Chrome on
  Windows) drops those photos with a message. The server also checks the file
  bytes and stores only JPEG, PNG or WebP. If a HEIC is refused, upload from
  Safari, or set iPhone Settings → Camera → Formats → Most Compatible.
* The website holds up to 400 boxes per photo (tested with 300: the page stays
  fast on a phone), so a whole-case photo also *works*. It's just slower to
  label and less accurate.
* Arrange the display the same way you normally do. The model counts
  **visible** corners. A ticket completely hidden behind another can't be
  counted.

## Step 2: label (about 5 minutes per photo, 1–2 once pre-filled)

On the label page:

1. **Rotate** (⟲ / ⟳) until the tickets read upright.
2. Pick the **value** ($5, $10, $20, $30, $50, or type another) and **tap the
   price corner of every ticket of that value**. Each tap stamps one box.
   Drag on an empty spot once to set the box size, and later taps reuse it.
   Then switch value and continue.
   **Keyboard:** type the value's digits to switch (`1` `0` = $10; `1`
   alone waits a moment in case you mean $10 or $100).
3. Fix mistakes: tap a box to select it and press a value button (or type the
   value) to change it. Drag a box to move it, drag its corner to resize, Delete/Backspace
   removes it. The **Boxes** list shows a zoomed crop of every box if you
   want to double-check.
4. Check the **tally** ("62 tickets · $5 41 · $10 21") against the photo,
   then **Save & next**.

Rules that keep the dataset clean:

| Situation | What to do |
|---|---|
| Corner partly overlapped, tilted, under glare, or cut off at the photo edge, but you can tell it's a separate ticket and its value | Box it. These hard cases are what the model must learn. |
| You can't tell the value, or whether it's a separate ticket | Don't box it. Never guess. |
| Prize text: "WIN UP TO $100,000", "PRIZES START AT $10", "$1,000,000" | Never box it. The model must learn these are not corners. |
| Box size | Cover the "$" value and the game number under it, plus a little margin. Keep boxes about the same size. |
| The whole photo is unusable | **Skip photo**. |
| The split dropdown | Leave it. It's chosen per day (70% train / 15% val / 15% test), so photos from one day never end up in both train and test. |

A photo counts as **labeled** once it has at least one box and every box has
a value.

## How many days?

The dashboard counts **labeled photos**. Each tray photo holds about 60
corners, so photos, not corners, are what take calendar time. At one round of
4 tray photos a day:

| Milestone | Labeled photos | Days of photos | What you do there |
|---|---|---|---|
| Baseline check | 10 | ~3 | Test Apple's OCR on whole photos (3b). It may already count well enough. |
| First trained models | 25 | ~1 week | Train detector + reader (3c, 3d), upload predictions (4) so labeling becomes checking. |
| Reliable counts | 80 | ~3 weeks | Exact counts on most photos, enough rare values ($4, $7, $50, $100). |

Labeling is the slower part: about 60 taps per tray photo, so roughly 3–4
minutes each by hand, under a minute each once predictions pre-fill them.

**Rare values** set the pace. The dashboard lists boxed tickets per value and
highlights any value with fewer than 40. If $50 stays rare, now and then take
an extra close-up photo of that section of the display, and still box every
corner in it.

## Step 3: train on the Mac

Run this whenever you pass a milestone, or once a week:

```bash
source ~/lotto-venv/bin/activate
cd SafeFamily

# 3a. Download "Training set (.zip)" from /lotto, then:
python scripts/lotto/prepare_dataset.py ~/Downloads/lotto-labeled-YYYYMMDD.zip
#    → lotto_data/yolo/ (detector data) and lotto_data/crops/ (reader data)
#    Open lotto_data/crops in Finder: each crop should be one upright price corner.

# 3b. Is training even needed? (first time, at ~10 photos)
python scripts/lotto/baseline_ocr.py --count --split test
#    Apple Vision counts "$5", "$10", … on whole photos. Exact on every photo → you may stop here.

# 3c. Corner detector (~20–60 min on an M-series Mac)
python scripts/lotto/train_detector.py
#    prints "you 91  model 90" per test photo, saves lotto_data/models/corner_detector.pt

# 3d. Value reader (~5–15 min)
python scripts/lotto/train_crnn.py
#    prints TEST accuracy per corner, saves lotto_data/models/lotto_crnn.pt
```

How to read the results:

* **Only the test photos count.** Train/val numbers look better than real life.
* The detector's first epochs show low scores. Let it run: it stops early by
  itself when it stops improving.
* The reader stays stuck near 0% for the first 20–30 epochs, then climbs
  quickly. That's normal. Keep the default 150 epochs.
* If train_crnn.py prints `WARNING: val has no $30`, the val/test photos
  contain no ticket of that value, so the scores can't tell you whether it's
  read right. Label more photos that include it. In a test run with too few
  $30 examples, every $30 was read as $20 while the other values were 100%
  right.
* If the reader confuses two values (`5` ↔ `50`), the crops may be cutting
  off digits: make boxes a bit wider when labeling.
* If the detector misses corners in one area (e.g. under glare), add photos
  with that problem.

## Step 4: bring predictions back

```bash
# Download "All photos, to pre-label (.zip)" from /lotto, then:
python scripts/lotto/predict.py ~/Downloads/lotto-all-YYYYMMDD.zip
#    prints per photo "model 90: $5×61, $10×17 …   you 91: …"
#    and writes predictions.json
```

Upload `predictions.json` on `/lotto`:

* **Waiting photos** get the model's boxes and values filled in. Boxes the
  model was unsure about are outlined in red. You fix mistakes instead of
  boxing everything.
* **Labeled photos** keep your labels untouched. Their card shows "Model: N
  ✓" or "off by K", and the progress panel shows on how many photos the count
  was exactly right. That is your real accuracy.

Repeat steps 1–4: more photos → better models → faster labeling.

## Later: count on the server (after the counts are reliable)

When the model gets every value exactly right on most test photos:

1. Copy both `.pt` files to the server and add a `/lotto/count` endpoint:
   upload photo → counts per value. Both models are small enough for the
   server's CPU, so no GPU is needed (adds `ultralytics` to the server image).
2. Feed the counts into the existing Store Accounting calculator.

Until then, treat the model as a helper whose counts you check.

## Reference

| Thing | Where |
|---|---|
| Web pages and API | `src/safe_family/lotto/lotto.py` (`/lotto`, `/lotto/<id>`, `/lotto/export.zip`, `/lotto/predictions`) |
| Table | `lotto_photos` (ORM model `LottoPhoto`; migrations in `scripts/migrate.py`) |
| Mac scripts | `scripts/lotto/`: `prepare_dataset.py`, `baseline_ocr.py`, `train_detector.py`, `train_crnn.py`, `predict.py` |
| Export format | `manifest.jsonl`: one JSON per photo `{id, file, rotation, split, skipped, labeled, boxes:[{x,y,w,h,label}]}`. Box coordinates are 0–1 fractions of the image **after** EXIF orientation and a clockwise `rotation`. `label` is the value, e.g. `"5"`. |
| predictions.json | `{"<photo id>": {"boxes": [{"x", "y", "w", "h", "text": "5", "conf": 0.93}, ...]}}`, same coordinates. |
