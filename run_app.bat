@echo off
REM ====================================================================
REM  Tillage image-pair study - LOCAL test launcher (Windows)
REM  Double-click to generate starter pairs (first time) and run the app.
REM  This is the LOCAL/testing backend. For the public emailed link,
REM  switch to Supabase + GitHub Pages (see README.md).
REM ====================================================================
cd /d "%~dp0"

if not exist "pairs_metadata.csv" (
    echo No image pairs found - generating synthetic starter set...
    python generate_pairs.py
)

echo.
echo Starting the local study app. Close this window (or Ctrl+C) to stop.
echo.
python app.py
pause
