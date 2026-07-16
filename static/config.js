/* =====================================================================
 *  STUDY CONFIG  -  this is the file you edit most.
 *  Change the questions, definitions, intro text, batch size, and which
 *  backend to use. No build step: just edit and refresh.
 * ===================================================================== */
window.STUDY_CONFIG = {

  /* ---- backend ------------------------------------------------------
   * "local"    -> talks to the Python app.py on your machine (for testing)
   * "supabase" -> talks to Supabase (for the public link you email out)
   * To go live: set this to "supabase" and fill in the two keys below
   * (Supabase dashboard -> Project Settings -> API).
   */
  backend: "supabase",
  supabaseUrl: "https://hpliztipokptoiwiouoa.supabase.co",
  supabaseAnonKey: "sb_publishable_HXAIQNMCL2LTIzbxyp2WsA_6Ixg3KXv",   // publishable key — safe in the browser

  /* ---- study parameters --------------------------------------------- */
  batchSize: 50,            // fields offered per session
  title: "Tillage Field Assessment",
  org: "Conservation Agriculture · Morocco",

  // 1 = ONE image per screen (the 8-date montage of a single field) + one question.
  // 2 = the old A/B pair mode (two fields side by side, one question each).
  imagesPerScreen: 1,

  // Project goal — drives the progress panel on the landing page.
  // 1 field = 1 image = 1 screen. Target = provinces × seasons × fieldsPerSeasonPerProvince.
  // Current pilot: Settat only, one season, 500 fields.
  goal: {
    provinces: 1,
    seasonStart: 2025,
    seasonEnd: 2025,
    fieldsPerSeasonPerProvince: 500,
  },

  /* ---- one-page intro (shown once, before labeling) -----------------
   * Plain HTML. Keep it to roughly one screen. This is where you teach
   * people how to answer correctly. Replace the placeholder text.        */
  introHtml: `
    <p>Thank you for helping us check our maps of <strong>tillage practices</strong>
    in Moroccan croplands. It takes about 10&ndash;15 minutes.</p>

    <h3>What you'll do</h3>
    <p>On each screen you'll see <strong>one field, shown at 8 dates</strong> across the
    season (every two weeks from September). The field is <strong>outlined in red</strong>.
    Answer <strong>one question</strong> &mdash; was it tilled? &mdash; then press
    <em>Next</em> for a new field. Your answers are saved automatically as you go.</p>

    <p class="muted">Watching the field <em>change over time</em> is the key: that's what
    reveals whether the soil was worked.</p>

    <h3>How to read the images</h3>
    <div class="def-grid">
      <div class="def">
        <span class="swatch till"></span>
        <div><strong>Tilled</strong> &mdash; the soil has been turned/worked.
        Look for <em>bare brown soil</em>, plough lines or furrows, little plant
        residue on the surface.</div>
      </div>
      <div class="def">
        <span class="swatch notill"></span>
        <div><strong>No-till</strong> &mdash; the soil was <em>not</em> worked.
        Look for a <em>greener, mottled surface</em> with straw/stubble
        (crop residue) left on top.</div>
      </div>
    </div>
    <p class="muted">If you genuinely cannot decide, choose <em>"Can't tell"</em> &mdash;
    that is more useful to us than a guess.</p>
  `,

  /* Optional short reminder available during labeling (the "Definitions" button). */
  quickRefHtml: `
    <p><span class="swatch till"></span><strong>Tilled:</strong> bare brown soil, furrows, little residue.</p>
    <p><span class="swatch notill"></span><strong>No-till:</strong> greener, straw/stubble residue on top.</p>
  `,

  /* ---- worked examples (shown on their own screen before labeling) ----
   * Two reference images with how-to-tell notes. Swap `src` for your own
   * clearest examples; the red arrow marks the field being judged.          */
  examples: {
    intro: "Two clear examples. In each, the red arrow marks the field you are judging.",
    items: [
      {
        src: "source/notill.jpg",
        label: "Tilled",
        points: [
          "Soil has been turned / worked before sowing",
          "Cultivated surface, little crop residue",
          "Here, the greener field",
        ],
      },
      {
        src: "source/till.jpg",
        label: "No-till",
        points: [
          "Soil left undisturbed — direct-seeded",
          "Crop residue / stubble kept on the surface",
          "Here, the reddish-brown field",
        ],
      },
    ],
  },

  /* ---- questions -----------------------------------------------------
   * Each question is a single choice from `options`.
   * `showIf: {question, equals}` makes a question CONDITIONAL — it only appears
   * once the referenced question has that answer, and its answer is dropped if
   * the condition stops being true. Only VISIBLE questions are required.
   *
   * The A..H labels must match the montage panels, i.e. the GEE settings
   * SEASON_START_MD=(9,1), N_STEPS=8, STEP_DAYS=14. Dates are year-agnostic,
   * so they hold for any season starting 1 September.                        */
  questions: [
    {
      id: "q_field",
      text: "Looking at the outlined field across the 8 dates &mdash; was it tilled?",
      imageRef: "a",
      options: [
        { value: "till",    label: "Tilled" },
        { value: "no_till", label: "No-till" },
        { value: "unsure",  label: "Can't tell" },
      ],
    },
    {
      id: "q_when",
      text: "In which image do you <strong>first</strong> see that it was tilled?",
      showIf: { question: "q_field", equals: "till" },
      options: [
        { value: "A", label: "A · 1 Sep" },
        { value: "B", label: "B · 15 Sep" },
        { value: "C", label: "C · 29 Sep" },
        { value: "D", label: "D · 13 Oct" },
        { value: "E", label: "E · 27 Oct" },
        { value: "F", label: "F · 10 Nov" },
        { value: "G", label: "G · 24 Nov" },
        { value: "H", label: "H · 8 Dec" },
        { value: "unsure", label: "Can't tell" },
      ],
    },
  ],

  requireAllAnswers: true,   // Next stays disabled until every VISIBLE question is answered
};
