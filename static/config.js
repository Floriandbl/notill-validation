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
    season (every two weeks from 1 September), labelled <strong>A</strong> to <strong>H</strong>.
    The field you are judging is <strong>outlined in magenta</strong>, with a dot on its centre.
    Answer <strong>one question</strong> &mdash; was it tilled? &mdash; then press
    <em>Next</em> for a new field. Your answers are saved automatically as you go.</p>

    <p class="muted">Watching the field <em>change from A to H</em> is the key: that's what
    reveals whether the soil was worked.</p>

    <h3>How to read the images</h3>
    <div class="devnote">
      Placeholder &mdash; to be written with Remote&nbsp;Sensing input.
    </div>
    <p class="muted">Here we can explain how to visually recognise <strong>Till</strong> by
    looking at &hellip; ; and the same for <strong>No-till</strong> by looking at &hellip;</p>

    <p class="muted">If you genuinely cannot decide, choose <em>"Can't tell"</em> &mdash;
    that is more useful to us than a guess.</p>
  `,

  /* Optional short reminder available during labeling (the "Definitions" button). */
  quickRefHtml: `
    <div class="devnote">Placeholder &mdash; to be written with Remote&nbsp;Sensing input.</div>
    <p class="muted"><strong>Till:</strong> look at &hellip;</p>
    <p class="muted"><strong>No-till:</strong> look at &hellip;</p>
    <p class="muted">The field under judgement is outlined in <strong>magenta</strong>.
    Panels run <strong>A&ndash;D</strong> on the top row, <strong>E&ndash;H</strong> on the bottom.</p>
  `,

  /* ---- worked examples (shown on their own screen before labeling) ----
   * Two REAL montages from the Settat 2025 set. They are placeholders chosen
   * automatically (biggest / smallest step-change in field texture) — NOT
   * verified ground truth. Swap `src` once a Remote Sensing expert has picked
   * the two clearest cases.                                                   */
  examples: {
    intro: "Two examples from the real image set. In each, the field you are judging is "
         + "outlined in magenta, and the 8 panels run A–D on the top row, E–H on the bottom.",

    // Shown in red, for development only — remove before circulating.
    devNote: "DEV NOTE — need to choose two good images for here.",

    // What we actually want people to look for.
    note: "The signal is a <strong>sudden change of texture</strong>: the surface inside the "
        + "field boundary (and sometimes in one or two neighbouring fields worked on the same "
        + "day) changes <strong>abruptly from one date to the next</strong>, while staying "
        + "relatively <strong>consistent before it and consistent after it</strong>. It is that "
        + "step — not the slow seasonal drift that every field shows — that indicates tillage.",

    items: [
      {
        src: "source/example_till.jpg",
        label: "Tilled",
        points: [
          "Texture changes abruptly between two consecutive dates",
          "Relatively consistent before the change, and again after it",
          "The change is confined to the outlined field (± a neighbour worked the same day)",
          "PLACEHOLDER — auto-selected, not expert-verified",
        ],
      },
      {
        src: "source/example_notill.jpg",
        label: "No-till",
        points: [
          "No abrupt step: texture stays consistent across all 8 dates",
          "Any change is gradual and shared with the whole landscape (season, rain)",
          "Surface keeps the same mottled residue appearance throughout",
          "PLACEHOLDER — auto-selected, not expert-verified",
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
      // "grid4" lays the options out 4-across, so the two rows of buttons line up
      // with the two rows of panels in the montage (A B C D / E F G H).
      // No "Can't tell" here on purpose: the labeler already said it was tilled,
      // so they must commit to a panel.
      layout: "grid4",
      options: [
        { value: "A", label: "A", sub: "1 Sep" },
        { value: "B", label: "B", sub: "15 Sep" },
        { value: "C", label: "C", sub: "29 Sep" },
        { value: "D", label: "D", sub: "13 Oct" },
        { value: "E", label: "E", sub: "27 Oct" },
        { value: "F", label: "F", sub: "10 Nov" },
        { value: "G", label: "G", sub: "24 Nov" },
        { value: "H", label: "H", sub: "8 Dec" },
      ],
    },
  ],

  requireAllAnswers: true,   // Next stays disabled until every VISIBLE question is answered
};
