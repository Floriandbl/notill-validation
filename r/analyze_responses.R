# =====================================================================
#  analyze_responses.R  —  coverage, agreement, timing-of-tillage, and QC
#  for the single-field / 8-date-montage design.
#
#  Input: responses_export.csv, taken from EITHER
#    - local test data : python export_responses.py
#    - live data       : run supabase/export_query.sql in the Supabase SQL
#                        Editor and Download CSV.
#  NOT the Table Editor's "Export -> CSV" button on `responses` — that dump
#  keeps the answers as one JSON blob and has no field_id. Guarded below.
#
#  Reads ./responses_export.csv (or ../responses_export.csv). No CLI argument.
#
#  Base R only. Cohen's kappa implemented inline.
# =====================================================================

app_dir  <- getwd()
csv_path <- file.path(app_dir, "responses_export.csv")
if (!file.exists(csv_path) && file.exists(file.path(app_dir, "..", "responses_export.csv"))) {
  csv_path <- normalizePath(file.path(app_dir, "..", "responses_export.csv"))
}
if (!file.exists(csv_path)) stop("responses_export.csv not found. Run: python export_responses.py")

d <- read.csv(csv_path, stringsAsFactors = FALSE)
cat("Loaded", nrow(d), "responses from", csv_path, "\n\n")

## ---- guard against the raw Supabase table dump -----------------------
## The Table Editor's "Export -> CSV" gives the unflattened table
## (id, pair_id, respondent, answers, created_at, meta, ip): the answers are
## still one JSON blob and there is no field_id, so everything below breaks
## with an unhelpful tapply error. Say so plainly instead.
if (!"field_id" %in% names(d)) {
  if ("pair_id" %in% names(d)) {
    stop("This looks like a raw Supabase table export (found 'pair_id', no 'field_id',\n",
         "  and the answers are still a JSON blob). Export it with the SQL in\n",
         "  supabase/export_query.sql instead — SQL Editor -> paste -> Run -> Download CSV.")
  }
  stop("No 'field_id' column in ", csv_path, ".\n",
       "  Expected columns: field_id, province, year, respondent, created_at, ip, q_field, ...\n",
       "  Produce it with `python export_responses.py` (local) or supabase/export_query.sql (live).")
}

## ---- coverage --------------------------------------------------------
raters_per_field <- tapply(d$respondent, d$field_id, function(x) length(unique(x)))
cat("== Coverage ==\n")
cat("  responses            :", nrow(d), "\n")
cat("  distinct fields seen :", length(raters_per_field), "\n")
cat("  fields with >=2 raters:", sum(raters_per_field >= 2), "\n")
cat("  contributors         :", length(unique(d$respondent)), "\n\n")

## ---- main answer: was it tilled? ------------------------------------
cat("== q_field (was it tilled?) ==\n")
if ("q_field" %in% names(d)) {
  print(table(d$q_field, useNA = "ifany"))
  cat("\n")
} else cat("  (no q_field column)\n\n")

## ---- conditional: when was it first visible? ------------------------
# Only asked when q_field == "till", so it is EXPECTED to be blank elsewhere.
cat("== q_when (first image showing tillage) — among 'till' answers ==\n")
if ("q_when" %in% names(d) && "q_field" %in% names(d)) {
  w <- d$q_when[d$q_field == "till" & !is.na(d$q_when) & d$q_when != ""]
  if (length(w)) {
    print(table(factor(w, levels = c(LETTERS[1:8], "unsure"))))
    cat("\n  (A=1 Sep, B=15 Sep, C=29 Sep, D=13 Oct, E=27 Oct, F=10 Nov, G=24 Nov, H=8 Dec)\n")
    stray <- sum(d$q_field != "till" & !is.na(d$q_when) & d$q_when != "")
    cat("  sanity — q_when set on a non-till answer:", stray, "(should be 0)\n\n")
  } else cat("  no 'till' answers yet\n\n")
} else cat("  (no q_when column)\n\n")

## ---- Cohen's kappa ---------------------------------------------------
cohen_kappa <- function(a, b) {
  lv <- sort(unique(c(a, b)))
  tab <- table(factor(a, lv), factor(b, lv))
  n <- sum(tab); if (n == 0) return(NA_real_)
  po <- sum(diag(tab)) / n
  pe <- sum(rowSums(tab) * colSums(tab)) / n^2
  if (pe == 1) return(NA_real_)
  (po - pe) / (1 - pe)
}

cat("== Inter-rater agreement on q_field (fields rated by >=2 people) ==\n")
multi <- names(raters_per_field[raters_per_field >= 2])
r1 <- c(); r2 <- c()
for (fid in multi) {
  a <- d$q_field[d$field_id == fid]
  a <- a[!is.na(a) & a != ""]
  if (length(a) >= 2) { r1 <- c(r1, a[1]); r2 <- c(r2, a[2]) }
}
if (length(r1)) {
  cat(sprintf("  n=%d  raw agreement=%.0f%%  kappa=%.2f\n",
              length(r1), 100 * mean(r1 == r2), cohen_kappa(r1, r2)))
} else cat("  no double-rated fields yet\n")
cat("\n")

## ---- QC on the technical context -------------------------------------
cat("== QC (technical context) ==\n")
if ("ip" %in% names(d))            cat("  distinct IPs        :", length(unique(d$ip[d$ip != ""])), "\n")
if ("meta_timezone" %in% names(d)) {
  tz <- d$meta_timezone[d$meta_timezone != ""]
  if (length(tz)) { cat("  timezones           :\n"); print(sort(table(tz), decreasing = TRUE)) }
}
if ("created_at" %in% names(d)) {
  ts <- as.POSIXct(d$created_at, format = "%Y-%m-%dT%H:%M:%S", tz = "UTC")
  ts <- ts[!is.na(ts)]
  if (length(ts)) {
    cat("  first / last answer :", format(min(ts)), "/", format(max(ts)), "\n")
    cat("  answers by hour (server clock):\n")
    print(table(as.integer(format(ts, "%H"))))
  }
}
cat("\n  Watch for: many answers from one IP under different names, or implausibly\n",
    " fast answering — both are quality flags, not proof of anything.\n")

## ---- responses per contributor ---------------------------------------
cat("\n== Responses per contributor ==\n")
print(sort(table(d$respondent), decreasing = TRUE))

cat("\nDone.\n")
