# =====================================================================
#  analyze_responses.R  -  coverage, inter-rater agreement, and (for the
#  synthetic starter set) accuracy of the crowd labels.
#
#  Input: responses_export.csv  (produce it with:  python export_responses.py)
#         For production data from Supabase, export the `responses` table to
#         CSV from the dashboard with the same columns and point `csv_path` to it.
#
#  Base R only (no packages needed). Cohen's kappa is implemented inline.
# =====================================================================

## ---- locate the export ---------------------------------------------
app_dir <- getwd()
csv_path <- file.path(app_dir, "responses_export.csv")
if (!file.exists(csv_path) && file.exists(file.path(app_dir, "..", "responses_export.csv"))) {
  csv_path <- normalizePath(file.path(app_dir, "..", "responses_export.csv"))
}
if (!file.exists(csv_path)) {
  stop("responses_export.csv not found. Run:  python export_responses.py")
}
d <- read.csv(csv_path, stringsAsFactors = FALSE)
cat("Loaded", nrow(d), "responses from", csv_path, "\n\n")

## ---- which answer columns exist? (everything that's not metadata) --
meta_cols  <- c("pair_id", "province", "year", "respondent", "created_at",
                "truth_a", "truth_b")
ans_cols   <- setdiff(names(d), meta_cols)
cat("Answer columns:", paste(ans_cols, collapse = ", "), "\n\n")

## ---- coverage -------------------------------------------------------
labelers_per_pair <- tapply(d$respondent, d$pair_id, function(x) length(unique(x)))
cat("== Coverage ==\n")
cat("  Pairs with >=1 response :", length(labelers_per_pair), "\n")
cat("  Pairs with 2 responses  :", sum(labelers_per_pair >= 2), "\n")
cat("  Distinct labelers       :", length(unique(d$respondent)), "\n")
cat("  Total responses         :", nrow(d), "\n\n")

## ---- answer distributions ------------------------------------------
cat("== Answer distributions ==\n")
for (q in ans_cols) {
  cat(" ", q, ":\n")
  print(table(d[[q]], useNA = "ifany"))
}
cat("\n")

## ---- Cohen's kappa (inline, base R) --------------------------------
cohen_kappa <- function(a, b) {
  lv <- sort(unique(c(a, b)))
  tab <- table(factor(a, lv), factor(b, lv))
  n <- sum(tab)
  if (n == 0) return(NA_real_)
  po <- sum(diag(tab)) / n
  pe <- sum(rowSums(tab) * colSums(tab)) / n^2
  if (pe == 1) return(NA_real_)
  (po - pe) / (1 - pe)
}

## ---- inter-rater agreement on pairs with exactly 2 labelers --------
cat("== Inter-rater agreement (pairs with 2 labelers) ==\n")
two <- names(labelers_per_pair[labelers_per_pair == 2])
for (q in ans_cols) {
  r1 <- c(); r2 <- c()
  for (pid in two) {
    sub <- d[d$pair_id == pid, ]
    a <- sub[[q]][!is.na(sub[[q]]) & sub[[q]] != ""]
    if (length(a) >= 2) { r1 <- c(r1, a[1]); r2 <- c(r2, a[2]) }
  }
  if (length(r1) == 0) { cat(" ", q, ": no double-labeled pairs yet\n"); next }
  agree <- mean(r1 == r2)
  k <- cohen_kappa(r1, r2)
  cat(sprintf("  %-6s  n=%-3d  raw agreement=%.0f%%  kappa=%.2f\n",
              q, length(r1), 100 * agree, k))
}
cat("\n")

## ---- accuracy vs synthetic truth (starter set only) ----------------
# Maps each answer column to a truth column by convention: q_a -> truth_a, q_b -> truth_b
if (all(c("truth_a", "truth_b") %in% names(d))) {
  cat("== Accuracy vs synthetic truth (synthetic chips only) ==\n")
  truth_map <- list(q_a = "truth_a", q_b = "truth_b")
  for (q in ans_cols) {
    tcol <- truth_map[[q]]
    if (is.null(tcol) || !(tcol %in% names(d))) next
    keep <- d[[q]] %in% c("till", "no_till") & d[[tcol]] %in% c("till", "no_till")
    if (!any(keep)) { cat(" ", q, ": nothing to score yet\n"); next }
    acc <- mean(d[[q]][keep] == d[[tcol]][keep])
    cat(sprintf("  %-6s  n=%-3d  accuracy=%.0f%%\n", q, sum(keep), 100 * acc))
  }
  cat("  (excludes 'unsure' answers and 'ambiguous' truth)\n")
}

cat("\nDone.\n")
