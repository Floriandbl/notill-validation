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
  batchSize: 50,            // pairs offered per session
  title: "Tillage Field Comparison",
  org: "Conservation Agriculture · Morocco",

  // Project goal — drives the progress panel on the landing page.
  // 1 field = 1 image; each pair shows 2 fields. Target = provinces × seasons ×
  // fieldsPerSeasonPerProvince. (20 × 11 × 100 = 22,000 fields = 11,000 pairs.)
  goal: {
    provinces: 20,
    seasonStart: 2015,
    seasonEnd: 2025,
    fieldsPerSeasonPerProvince: 100,
  },

  /* ---- one-page intro (shown once, before labeling) -----------------
   * Plain HTML. Keep it to roughly one screen. This is where you teach
   * people how to answer correctly. Replace the placeholder text.        */
  introHtml: `
    <p>Thank you for helping us check our maps of <strong>tillage practices</strong>
    in Moroccan croplands. It takes about 10&ndash;15 minutes.</p>

    <h3>What you'll do</h3>
    <p>On each screen you'll see <strong>two field images (A and B)</strong> and answer
    <strong>two short questions</strong>, then press <em>Next</em> for a new pair.
    Your answers are saved automatically as you go.</p>

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
        src: "source/till.jpg",
        label: "Tilled",
        points: [
          "Bare, reddish-brown soil",
          "Visible plough lines / furrows",
          "Little or no crop residue on the surface",
        ],
      },
      {
        src: "source/notill.jpg",
        label: "No-till",
        points: [
          "Greener surface — vegetation or cover",
          "Crop residue / stubble left on top",
          "Soil has not been turned/worked",
        ],
      },
    ],
  },

  /* ---- the two questions --------------------------------------------
   * Each question is a single choice from `options`.
   * `imageRef`: "a", "b", or null  (used only to label which image it's about)
   * Add/remove options freely; `value` is what gets stored, `label` is shown.   */
  questions: [
    {
      id: "q_a",
      text: "Image A &mdash; what is the tillage status of this field?",
      imageRef: "a",
      options: [
        { value: "till",    label: "Tilled" },
        { value: "no_till", label: "No-till" },
        { value: "unsure",  label: "Can't tell" },
      ],
    },
    {
      id: "q_b",
      text: "Image B &mdash; what is the tillage status of this field?",
      imageRef: "b",
      options: [
        { value: "till",    label: "Tilled" },
        { value: "no_till", label: "No-till" },
        { value: "unsure",  label: "Can't tell" },
      ],
    },
  ],

  requireAllAnswers: true,   // Next stays disabled until both questions answered
};
