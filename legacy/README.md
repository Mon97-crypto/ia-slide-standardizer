# Legacy: IA Slide Standardizer

The original tool this repository started as. It converts a PPTX or a screenshot
into an on-brand Impact Analytics deck.

It is kept here unchanged and is no longer the deployed application. To run it:

```bash
pip install flask python-pptx Pillow pytesseract gunicorn
python legacy/slide_standardizer/app.py
```
