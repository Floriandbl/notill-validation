# =====================================================================
#  build_pairs.R  -  turn the images/ folder into the `pairs` seed data.
#
#  Reads pairs_metadata.csv (written by generate_pairs.py), builds the
#  public jsDelivr CDN URLs for each image, and writes:
#     pairs_for_supabase.csv   <- import via Supabase Table editor
#     pairs_seed.sql           <- or paste into the Supabase SQL editor
#
#  Base R only (no packages needed).
# =====================================================================

## ---- 1. EDIT THESE to point at your public GitHub repo --------------
gh_user   <- "YOUR_GITHUB_USERNAME"
gh_repo   <- "YOUR_REPO_NAME"      # the repo that contains the images/ folder
gh_branch <- "main"               # branch or tag

## ---- 2. paths -------------------------------------------------------
# Set this to your App/ folder, or just run R from inside App/.
app_dir <- getwd()
if (!file.exists(file.path(app_dir, "pairs_metadata.csv")) &&
    file.exists(file.path(app_dir, "..", "pairs_metadata.csv"))) {
  app_dir <- normalizePath(file.path(app_dir, ".."))
}
meta_path <- file.path(app_dir, "pairs_metadata.csv")
if (!file.exists(meta_path)) {
  stop("pairs_metadata.csv not found. Set app_dir to your App/ folder ",
       "(run generate_pairs.py first). Current app_dir = ", app_dir)
}

meta <- read.csv(meta_path, stringsAsFactors = FALSE)

## ---- 3. build CDN URLs ---------------------------------------------
cdn <- function(relpath) {
  sprintf("https://cdn.jsdelivr.net/gh/%s/%s@%s/images/%s",
          gh_user, gh_repo, gh_branch, relpath)
}
out <- data.frame(
  pair_id  = meta$pair_id,
  province = meta$province,
  year     = meta$year,
  image_a  = vapply(meta$image_a, cdn, character(1)),
  image_b  = vapply(meta$image_b, cdn, character(1)),
  stringsAsFactors = FALSE
)

## ---- 4a. CSV for the Supabase Table editor -------------------------
csv_path <- file.path(app_dir, "pairs_for_supabase.csv")
write.csv(out, csv_path, row.names = FALSE, na = "")
cat("Wrote", nrow(out), "rows ->", csv_path, "\n")

## ---- 4b. SQL seed (INSERT ... ON CONFLICT DO NOTHING) --------------
esc <- function(x) gsub("'", "''", x, fixed = TRUE)
vals <- sprintf("  ('%s','%s',%s,'%s','%s')",
                esc(out$pair_id), esc(out$province),
                ifelse(is.na(out$year), "null", out$year),
                esc(out$image_a), esc(out$image_b))
sql <- paste0(
  "insert into public.pairs (pair_id, province, year, image_a, image_b) values\n",
  paste(vals, collapse = ",\n"),
  "\non conflict (pair_id) do nothing;\n")
sql_path <- file.path(app_dir, "pairs_seed.sql")
writeLines(sql, sql_path)
cat("Wrote SQL seed ->", sql_path, "\n")

cat("\nNext steps:\n",
    " 1. Push the App/images folder to a PUBLIC GitHub repo (", gh_user, "/", gh_repo, ").\n",
    " 2. Load the pairs: import pairs_for_supabase.csv OR run pairs_seed.sql in Supabase.\n",
    " 3. Set backend:'supabase' + keys in static/config.js and deploy to GitHub Pages.\n", sep = "")
