# Lotto ticket-number recognizer: the full plan

Goal: take a photo of the lotto tickets and have the computer read the
**ticket number printed in the top-left corner** of each ticket, so counting
sold tickets no longer needs typing.

Everything except training happens on the website (`/lotto`, the **Lotto** tab).
Training happens on the Mac, because the Linux server has no GPU. You move one
zip file to the Mac and one JSON file back.

```
 phone / browser                 SafeFamily server (no GPU)                 Mac (Apple GPU)
 ───────────────                 ──────────────────────────                 ───────────────
 1. take photo  ──upload──▶  stores original untouched
                             2. label page: rotate, box, type the number
                             progress + days-left estimate
                             ⬇ export.zip (images + manifest.jsonl)  ──▶  3a prepare_dataset.py (crop + rotate)
                                                                          3b baseline_ocr.py   (is training needed?)
                                                                          3c train_crnn.py     (GPU, minutes)
                             ⬆ predictions.json  ◀──────────────────────  4  predict.py
                             new photos arrive pre-filled:
                             labeling becomes "check and fix"
```

## Why it is built this way

* **The original photo is never changed.** Rotation and boxes are saved as
  numbers next to it. If you box something wrong, fix it and nothing is lost.
  The Mac scripts apply the same rotation and crop, so what you saw on the
  label page is exactly what the model trains on.
* **One box per number, not per photo.** A photo of the dispenser can show
  many tickets. Each boxed number is one training example, so one photo can
  count as 10 or more examples instead of one. This is the biggest lever on
  how many days you need (see the table below).
* **Boxes are copied from the previous photo.** The tickets sit in the same
  slots every day. A new upload starts with yesterday's box positions, so you
  nudge boxes and type numbers instead of drawing everything again.
* **The server only stores files.** No image libraries and no GPU on the
  server. All heavy work runs on the Mac.

## Step 0: one-time setup

Server (after pulling this change):

```bash
docker-compose up -d --build app
docker compose exec app python scripts/migrate.py   # creates the lotto_photos table
```

Mac (Apple silicon, Python 3.11+):

```bash
git clone <this repo> && cd SafeFamily        # or just copy scripts/lotto/
python3 -m venv ~/lotto-venv && source ~/lotto-venv/bin/activate
pip install torch torchvision pillow          # PyTorch ships with Apple-GPU (MPS) support
pip install ocrmac                            # optional: Apple Live Text OCR for the baseline
```

Check that the Mac GPU is visible:
`python -c "import torch; print(torch.backends.mps.is_available())"` should
print `True`.

## Step 1: take photos (every day, about 1 minute)

Open `/lotto` on your phone, tap **Choose / take photos**, then **Upload**.

Good photos:

* The whole number is sharp, and each digit is at least ~20 px tall in the
  photo. Get closer rather than zooming.
* No glare across the numbers. Tilt the phone a little if the plastic reflects.
* **Vary it on purpose:** morning and evening light, slightly different
  angles, different ticket games. The model only learns what it has seen.
* Bad photos are fine too. If you will use the model on blurry photos one
  day, it needs a few blurry ones to learn from.

On an iPhone, Safari converts HEIC photos to JPEG on upload. If a photo ever
shows "Could not load the image", export it as JPEG first.

## Step 2: label (about 1 to 2 minutes per photo)

On the label page:

1. **Rotate** (⟲ / ⟳) until the numbers read upright.
2. **Drag** a box around each ticket number. Make it tight, with a little
   margin, and box only the number, not the game name. **Tap** to stamp a box
   the same size as the last one. Drag a box to move it, drag its corner to
   resize, and press Delete/Backspace to remove the selected box. On a phone,
   use **Zoom**, and turn on **Pan** to scroll around.
3. **Type** the number exactly as printed, **leading zeros included**
   (`007`, not `7`). Read it from the zoomed preview next to the input, not
   from the big photo. **Enter** moves to the next box, and Enter on the last
   box saves.
4. **Save & next.**

Rules that keep the dataset clean:

| Situation | What to do |
|---|---|
| A number is partly hidden, blurry or cut off, but **you** can still read it for sure | Box it and label it. These examples are valuable. |
| You can't read it for sure | Delete that box. Never guess: a wrong label teaches the model a mistake. |
| The whole photo is useless | **Skip photo**. It is kept but left out of training. |
| Same ticket appears in two photos | Fine, label both. |
| The split dropdown | Leave it. It is chosen per day: 70% train, 15% val, 15% test. **test** photos are never trained on, so they give an honest accuracy score. |

A photo only counts as **labeled** once it has at least one box and every box
has a number. Otherwise it is saved as a draft and stays in "To label".

## How many days?

The dashboard shows a live "days left" for each milestone, based on your real
numbers-per-photo. The three milestones count labeled **numbers (boxes)**:

| Milestone | Numbers | What you do there |
|---|---|---|
| Baseline check | 60 | Test off-the-shelf OCR (step 3b). It may already be good enough. |
| First trained model | 300 | Train (3c), expect ~80–95%, then pre-label with predictions (4). |
| Solid model | 1,000 | ~99% per number is realistic for printed digits. |

At **2 photos a day**:

| Numbers per photo | Baseline (60) | First model (300) | Solid (1,000) |
|---|---|---|---|
| 1 (a single ticket per photo) | 30 days | 150 days | 500 days |
| 5 | 6 days | 30 days | 100 days |
| 10 (one dispenser row) | 3 days | 15 days | 50 days |
| 20 | 2 days | 8 days | 25 days |

So: **put as many tickets as you can into each photo, and box every number.**
With ~10 numbers per photo you reach a first model in about two weeks, and a
solid one in under two months. Printed digits in one font are an easy task:
heavy augmentation in training turns 300 real examples into many thousands of
slightly tilted, blurred and re-lit variations.

Ways to go faster without hurting quality:

* Take more than 2 photos on some days, for example after restocking. Photos
  from the same day always share a split, so extra shots of the same scene
  can't leak from train into test.
* After the first model, upload `predictions.json` (step 4). Labeling becomes
  checking and fixing, which is about 3× faster.

## Step 3: train on the Mac

Run this whenever you pass a milestone, or once a week:

```bash
source ~/lotto-venv/bin/activate
cd SafeFamily

# 3a. Download "Training set (.zip)" from /lotto, then:
python scripts/lotto/prepare_dataset.py ~/Downloads/lotto-labeled-YYYYMMDD.zip
#    → lotto_data/crops/{train,val,test}/*.png  + train/val/test.tsv
#    Open lotto_data/crops in Finder: every crop should be upright and tight.

# 3b. Is training even needed? (first time, at ~60 numbers)
python scripts/lotto/baseline_ocr.py --engine vision --split test
#    98%+ → off-the-shelf OCR is enough; you can stop here.

# 3c. Train (needs ~300 numbers to be worthwhile)
python scripts/lotto/train_crnn.py
#    prints val accuracy while training, then TEST accuracy and every miss.
#    Model saved to lotto_data/models/lotto_crnn.pt
```

How to read the result:

* **Only the TEST accuracy counts.** Train/val numbers look better than real
  life.
* Look at the misses it prints. If the *label* is wrong, fix it on the website.
  This happens more often than you'd expect. If one digit pair is always
  confused (`1`↔`7`, `0`↔`8`), add more photos with those digits.
* Expected roughly: 300 numbers → 80–95%, 1,000 numbers → 98–99.5%.
  (A test run on 258 synthetic training numbers reached 83% on test.)
* **The first 20–30 epochs look stuck**: loss hovers around 1.5 and val stays
  near 0%. That is normal for CTC models. Accuracy then climbs quickly. Don't
  cut training short. Keep the default 150 epochs.

What the model is: a small **CRNN with CTC loss**, about 1M parameters. A CNN
reads the 32×128 grayscale crop as 32 vertical slices, a BiLSTM reads them
left to right, and CTC lets it output any number of digits without boxing each
digit. It trains in minutes on an M-series GPU. It is also small enough to run
on the server's CPU later.

## Step 4: bring predictions back (model-assisted labeling)

```bash
# Download "All photos, to pre-label (.zip)" from /lotto, then:
python scripts/lotto/predict.py ~/Downloads/lotto-all-YYYYMMDD.zip
#    → predictions.json  (also prints accuracy on already-labeled boxes)
```

Upload `predictions.json` on `/lotto`. Every box now shows the model's guess,
already filled into the input. Guesses under 90% confidence get a red outline.
You only correct the wrong ones. Human labels are never overwritten. A
prediction only fills an empty box.

Repeat steps 1–4: more photos → better model → faster labeling.

## Later: use it for counting (phase 5, after the model is solid)

The model above only *reads* numbers. To use it in the store:

1. Copy `lotto_crnn.pt` to the server and add a `/lotto/read` endpoint that
   runs it on CPU. The model is small, so no GPU is needed for inference. This
   adds `torch` (CPU wheel) or `onnxruntime` to the server image.
2. Box positions are fixed per dispenser slot, so the saved boxes double as
   the "where to look" map: photo in, one number per slot out.
3. Tickets sold per slot = yesterday's number − today's number (or the other
   way round, depending on how the pack counts), times the price, which feeds
   the existing Store Accounting calculator.

Don't build phase 5 until the TEST accuracy is consistently above 99%. Until
then, use the predictions as suggestions you check.

## Reference

| Thing | Where |
|---|---|
| Web pages and API | `src/safe_family/lotto/lotto.py` (`/lotto`, `/lotto/<id>`, `/lotto/export.zip`, `/lotto/predictions`) |
| Table | `lotto_photos` (ORM model `LottoPhoto`; migration in `scripts/migrate.py`) |
| Mac scripts | `scripts/lotto/` (`prepare_dataset.py`, `baseline_ocr.py`, `train_crnn.py`, `predict.py`) |
| Export format | `manifest.jsonl`: one JSON per photo `{id, file, rotation, split, skipped, labeled, boxes:[{x,y,w,h,label,pred?,conf?}]}`. Box coordinates are 0–1 fractions of the image **after** EXIF orientation and a clockwise `rotation`. |
| predictions.json | `{"<photo id>": [{"text": "007", "conf": 0.98}, ...]}`, one entry per box, in box order. |
