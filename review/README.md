# Native-speaker review

Every published word already passed the automatic checks in `tools/verify_words.py` and a first hand review.
A native speaker gives the final sign-off.

1. Open `review/te/expert_review.tsv` (Telugu) or `review/hi/expert_review.tsv` (Hindi) in Excel, Google Sheets
   or LibreOffice. It lists about 1,000-1,300 words: the most common, a random sample, the rarest, allow-listed
   words and the app's hand-made words that no corpus confirms.
2. In the `decision` column write `ok`, `wrong` or `offensive`. For `wrong`, write the right spelling in
   `correct_spelling`. Save as tab-separated text with the same name.
3. Run `python tools/apply_review.py --apply te --reviewer "Name"`, then rebuild with a higher version:
   `python tools/verify_words.py --version 2 --app-src <unpacked app source>`.
   (The rebuild needs the `work/` data: re-run Actions > "Collect word data" on a `build/...` branch first.)

Other files here: `rejected.tsv.gz` (every rejected word and why), `builtin_check.tsv.gz` (app built-in lists),
`top_500.tsv`, `random_300.tsv`, `tail_200.tsv`, `verification_report.json`.
