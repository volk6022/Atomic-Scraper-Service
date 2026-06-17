// Mock dataset for the review app prototype.
// Contains the real Adv. Fremm sample + 11 synthesized cards across different states.

const SAMPLE_TRACE_FREMM = [
  { turn: 1, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм Санкт-Петербург"}', elapsed_s: 2.23, tokens: 1553 },
  { turn: 1, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм Санкт-Петербург","count":6,"results":[{"url":"https://yandex.ru/maps/org/advokat_fremm/1000341388/","title":"Адвокат Фремм, адвокаты, Стремянная ул., 11, Санкт-Петербург — Яндекс Карты","snippet":"Команда профессионалов работает с 90-х годов прошлого века! Представительный офис в центре СПб..."}]}', elapsed_s: 6.76 },
  { turn: 2, role: "assistant", tool: "web_scrape", args: '{"url":"https://www.fremm.ru/"}', elapsed_s: 3.97, tokens: 2351 },
  { turn: 2, role: "tool", tool: "web_scrape", preview: '{"url":"https://www.fremm.ru/","error":"","text":"","length":0,"ok":false}', elapsed_s: 15.01, ok: false },
  { turn: 2, role: "tool", tool: "web_scrape", preview: '{"url":"https://www.advocatefremm.ru/o-kompanii","error":"","text":"","length":0,"ok":false}', elapsed_s: 15.01, ok: false },
  { turn: 2, role: "tool", tool: "web_scrape", preview: '{"url":"https://vk.com/abfremm","error":"","text":"","length":0,"ok":false}', elapsed_s: 15.01, ok: false },
  { turn: 3, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм сайт"}', elapsed_s: 3.54, tokens: 2570 },
  { turn: 3, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм сайт","count":6,"results":[...]}', elapsed_s: 4.59 },
  { turn: 4, role: "assistant", tool: "web_scrape", args: '{"url":"https://www.fremm.spb.ru/"}', elapsed_s: 4.2, tokens: 3120 },
  { turn: 4, role: "tool", tool: "web_scrape", preview: '{"url":"https://www.fremm.spb.ru/","text":"Адвокат ФРЕММ. Юридическое сопровождение. Более чем за четверть века работы компания зарекомендовала себя в качестве надёжного и профессионального юридического консультанта...","length":4280,"ok":true}', elapsed_s: 8.4, ok: true },
  { turn: 5, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм контакты телефон"}', elapsed_s: 3.1, tokens: 4220 },
  { turn: 5, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм контакты телефон","count":6,"results":[...]}', elapsed_s: 3.9 },
  { turn: 6, role: "assistant", tool: "web_scrape", args: '{"url":"https://nsp.ru/companies/543-advokat-fremm"}', elapsed_s: 4.8, tokens: 5180 },
  { turn: 6, role: "tool", tool: "web_scrape", preview: '{"url":"https://nsp.ru/companies/543-advokat-fremm","text":"Адвокатская фирма Фремм создана в 1993 году группой выпускников юрфака СПбГУ. Офис на Стремянной улице. Арбитражная практика, регистрация юридических лиц...","length":2840,"ok":true}', elapsed_s: 6.2, ok: true },
  { turn: 7, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм habr"}', elapsed_s: 2.8, tokens: 6020 },
  { turn: 7, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм habr","count":0,"results":[]}', elapsed_s: 2.1 },
  { turn: 8, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм соцсети"}', elapsed_s: 2.5, tokens: 6240 },
  { turn: 8, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм соцсети","count":4,"results":[{"url":"https://vk.com/advokat_fremm",...}]}', elapsed_s: 3.4 },
  { turn: 9, role: "assistant", tool: "web_scrape", args: '{"url":"https://spb.hh.ru/employer/166622"}', elapsed_s: 3.9, tokens: 7180 },
  { turn: 9, role: "tool", tool: "web_scrape", preview: '{"url":"https://spb.hh.ru/employer/166622","text":"Адвокат ФРЕММ. Юридические услуги. Вакансии: Бухгалтер (89462161), Курьер (23642352), Управляющий агентством коммерческой недвижимости (2899653)...","length":3120,"ok":true}', elapsed_s: 5.1, ok: true },
  { turn: 10, role: "assistant", tool: "web_scrape", args: '{"url":"https://dreamjob.ru/employers/26921/..."}', elapsed_s: 3.1, tokens: 8460 },
  { turn: 10, role: "tool", tool: "web_scrape", preview: '{"url":"https://dreamjob.ru/employers/26921/...","text":"Адвокат ФРЕММ — юридическая компания, размер: меньше 100 сотрудников. Отзывы сотрудников...","length":1840,"ok":true}', elapsed_s: 4.7, ok: true },
  { turn: 11, role: "assistant", tool: "web_serp", args: '{"query":"Адвокат Фремм отзывы"}', elapsed_s: 2.2, tokens: 9320 },
  { turn: 11, role: "tool", tool: "web_serp", preview: '{"query":"Адвокат Фремм отзывы","count":6,"results":[{"url":"https://zoon.ru/spb/law/yuridicheskaya_kompaniya_advokat_fremm/",...}]}', elapsed_s: 2.8 },
  { turn: 12, role: "assistant", tool: "submit_org_card", args: '{...полная карточка...}', elapsed_s: 4.5, tokens: 10941 },
  { turn: 12, role: "critic", score: 9.0, verdict: "pass", feedback: "Strong card with diverse sources and verified phone numbers. Empty tech_stack is acceptable for a law firm. All core fields populated with grounded data.", missing: ["tech_stack (not applicable for law firm)", "problems_signals (optional)"], wrong: [] },
];

const FREMM_CARD = {
  oid: "1000341388",
  model_key: "local",
  name: "Адвокат Фремм",
  anchor: {
    name: "Адвокат Фремм",
    oid: "1000341388",
    address: "Санкт-Петербург, Стремянная улица, 11",
    city: "Санкт-Петербург",
    categories: ["Адвокаты", "юридические услуги", "бухгалтерские услуги"],
    yandex_phones: ["+7 (812) 575-80-80", "+7 (812) 575-80-08"],
    yandex_site: null,
    yandex_url: "https://yandex.ru/maps/org/advokat_fremm/1000341388",
  },
  critic_score: 9.0,
  critic_verdict: "pass",
  critic_feedback: "Strong card with diverse sources and verified phone numbers. Empty tech_stack is acceptable for a law firm.",
  turns: 12,
  elapsed_s: 462.1,
  tokens: { main: { prompt: 72876, completion: 3913, last_prompt: 10941 }, aux: { prompt: 1573, completion: 430 }, grand_total: 78792 },
  tool_call_counts: { web_serp: 11, web_scrape: 18, submit_org_card: 1 },
  refraser_runs: 0,
  submit_attempts: 1,
  compactions: 0,
  forced_submit: false,
  blocked_domains: ["www.fremm.ru"],
  review_status: "new",
  card: {
    what_they_do: "Юридическая фирма «Адвокат ФРЕММ» создана в 1993 году группой выпускников юрфака СПбГУ. Занимается представлением интересов клиентов в судах (арбитражная практика), регистрацией юридических лиц, юридическим и бухгалтерским сопровождением, представлением интересов в суде, юридическим сопровождением, регистрацией и ликвидацией компаний, бухгалтерским сопровождением.",
    scale_indicators: [
      "Создана в 1993 году — одна из старейших юридических фирм в Санкт-Петербурге",
      "Меньше 100 сотрудников (по dreamjob.ru)",
      "Офис на Стремянной улице в центре Санкт-Петербурга с 1995 года",
      "4.9 рейтинг на Яндекс.Картах (20 отзывов)",
      "Присутствует в рейтингах лучших юридических компаний России",
    ],
    tech_stack: [],
    vacancies: [
      { title: "Бухгалтер", url: "https://spb.hh.ru/vacancy/89462161", platform: "hh.ru" },
      { title: "Курьер", url: "https://spb.hh.ru/vacancy/23642352", platform: "hh.ru" },
      { title: "Управляющий агентством коммерческой недвижимости", url: "https://spb.hh.ru/vacancy/2899653", platform: "hh.ru" },
    ],
    social: {
      vk: ["https://vk.com/abfremm", "https://vk.com/advokat_fremm"],
      telegram: [],
      instagram: [],
      youtube: [],
      linkedin: [],
      habr: [],
    },
    contacts: {
      phones: [
        { number: "+7 (812) 575-80-80", context: "Яндекс.Карты (официальный номер)" },
        { number: "+7 (812) 575-80-08", context: "Яндекс.Карты, также указан на сайте" },
      ],
      emails: [],
      websites: ["https://www.fremm.ru/", "https://www.advocatefremm.ru/", "https://www.fremm.spb.ru/"],
    },
    yandex_maps: {
      rating: 4.9,
      reviews_count: 20,
      reviews_sample: [
        "Команда профессионалов работает с 90-х годов прошлого века! Представительный офис в центре СПб.",
        "Индивидуальный подход. Работают на результат — это чувствуется.",
        "Сложные вопросы обсуждают командой юристов. Имеют огромный опыт в судебных спорах.",
      ],
      hours: "",
    },
    problems_signals: [],
    sources: [
      { url: "https://yandex.ru/maps/org/advokat_fremm/1000341388/", what_it_provided: "Рейтинг 4.9, 20 отзывов, телефоны" },
      { url: "https://www.fremm.ru/", what_it_provided: "Основная информация о компании, подтверждено через поисковые отрывки" },
      { url: "https://www.advocatefremm.ru/", what_it_provided: "Информация о компании и услугах" },
      { url: "https://vk.com/abfremm", what_it_provided: "Социальные сети компании" },
      { url: "https://vk.com/advokat_fremm", what_it_provided: "ВКонтакте страница компании" },
      { url: "https://nsp.ru/companies/543-advokat-fremm", what_it_provided: "Основание компании 1993, выпускники СПбГУ, сфера деятельности" },
      { url: "https://spb.hh.ru/employer/166622", what_it_provided: "Информация о вакансии и компании" },
      { url: "https://dreamjob.ru/employers/26921/city-sankt-peterburg/vacancy-pomoschnik-yurista", what_it_provided: "Вакансии компании, размер штата" },
    ],
  },
  queries_history: [
    "Адвокат Фремм Санкт-Петербург",
    "Адвокат Фремм сайт",
    "Адвокатское бюро ФРЕММ СПб",
    "Адвокат Фремм контакты телефон",
    "Адвокат Фремм услуги",
    "Адвокат Фремм habr",
    "Адвокат Фремм соцсети",
    "Адвокат Фремм отзывы",
    "Адвокат Фремм hh.ru vacancies",
    "Адвокат Фремм superjob",
    "Адвокат Фремм vacancies hh.ru",
  ],
  visited_urls: [
    "https://dreamjob.ru/employers/26921/city-sankt-peterburg/vacancy-pomoschnik-yurista",
    "https://nsp.ru/companies/543-advokat-fremm",
    "https://sankt-peterburg1.jsprav.ru/yuridicheskie-uslugi/advokat-fremm/",
    "https://spb.hh.ru/employer/166622",
    "https://spb.spravka.city/company/advokat-fremm",
    "https://spb.spravker.ru/juristy/advokat-fremm.htm",
    "https://vk.com/abfremm",
    "https://vk.com/advokat_fremm",
    "https://www.advocatefremm.ru/",
    "https://www.advocatefremm.ru/o-kompanii",
    "https://www.fremm.ru/",
    "https://www.fremm.ru/kontakty",
    "https://www.fremm.ru/uslugi",
    "https://www.fremm.spb.ru/",
    "https://www.fremm.spb.ru/kontakty",
    "https://zoon.ru/spb/law/yuridicheskaya_kompaniya_advokat_fremm/",
  ],
  trace: SAMPLE_TRACE_FREMM,
  critic_events: [{
    turn: 12, role: "critic", score: 9.0, verdict: "pass",
    missing: ["tech_stack (not applicable for law firm)", "problems_signals (optional)"],
    wrong: [],
    feedback: "Strong card with diverse sources and verified phone numbers. Empty tech_stack is acceptable for a law firm. All core fields populated with grounded data.",
  }],
};

// Synthesized cards covering different states/categories
const MOCK_CARDS = [
  FREMM_CARD,

  // High-score IT
  {
    oid: "1024518739", model_key: "local", name: "Студия Тёмное Время",
    anchor: { name: "Студия Тёмное Время", oid: "1024518739", address: "Санкт-Петербург, наб. Обводного канала, 199", city: "Санкт-Петербург", categories: ["Веб-разработка", "дизайн-студия"], yandex_phones: ["+7 (812) 244-30-77"], yandex_site: "https://temnoevr.com", yandex_url: "https://yandex.ru/maps/org/1024518739" },
    critic_score: 9.4, critic_verdict: "pass", critic_feedback: "Полная карточка, верифицированный сайт, активный hh.ru/Habr.",
    turns: 9, elapsed_s: 312.4, tokens: { main: { prompt: 48210, completion: 2810, last_prompt: 8244 }, aux: { prompt: 920, completion: 310 }, grand_total: 52250 },
    tool_call_counts: { web_serp: 8, web_scrape: 14, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "reviewed",
    card: {
      what_they_do: "Дизайн-студия и веб-разработка. Создаёт сайты, мобильные приложения и брендинг для российских и зарубежных клиентов с 2014 года. Фокус на сложных пользовательских интерфейсах и моушн-дизайне.",
      scale_indicators: ["~40 сотрудников по данным hh.ru", "Резиденты IT-кластера ИТМО Хайпарк", "Клиенты: Тинькофф, Авито, ВКонтакте (по портфолио)"],
      tech_stack: ["React", "TypeScript", "Next.js", "Figma", "Webflow", "Node.js"],
      vacancies: [
        { title: "Senior Frontend Developer", url: "https://hh.ru/vacancy/91827361", platform: "hh.ru" },
        { title: "Motion-дизайнер", url: "https://hh.ru/vacancy/91827382", platform: "hh.ru" },
      ],
      social: { vk: ["https://vk.com/temnoevremya"], telegram: ["https://t.me/temnoevr_studio"], instagram: [], youtube: ["https://youtube.com/@temnoevr"], linkedin: [], habr: ["https://habr.com/ru/companies/temnoevr/"] },
      contacts: { phones: [{ number: "+7 (812) 244-30-77", context: "официальный сайт" }], emails: [{ address: "hi@temnoevr.com", context: "контактная форма" }], websites: ["https://temnoevr.com"] },
      yandex_maps: { rating: 4.8, reviews_count: 47, reviews_sample: ["Отлично сделали сайт под ключ", "Креативно и в срок"], hours: "Пн-Пт 10:00-19:00" },
      problems_signals: [],
      sources: [
        { url: "https://temnoevr.com", what_it_provided: "услуги, контакты, портфолио" },
        { url: "https://habr.com/ru/companies/temnoevr/", what_it_provided: "технологический стек, статьи команды" },
        { url: "https://hh.ru/employer/892341", what_it_provided: "размер команды, открытые вакансии" },
      ],
    },
    queries_history: ["Студия Тёмное Время СПб", "temnoevr habr", "Тёмное Время hh.ru"], visited_urls: ["https://temnoevr.com", "https://habr.com/ru/companies/temnoevr/", "https://hh.ru/employer/892341"],
    trace: [], critic_events: [{ turn: 9, role: "critic", score: 9.4, verdict: "pass", missing: [], wrong: [], feedback: "Полная карточка." }],
  },

  // Low-score, forced submit (legal-ish vacuum)
  {
    oid: "1338920147", model_key: "local", name: "ООО Промтехресурс",
    anchor: { name: "ООО Промтехресурс", oid: "1338920147", address: "Санкт-Петербург, Лиговский пр., 87, лит. А", city: "Санкт-Петербург", categories: ["Снабжение", "оптовая торговля"], yandex_phones: ["+7 (812) 318-22-11"], yandex_site: null, yandex_url: "https://yandex.ru/maps/org/1338920147" },
    critic_score: 4.5, critic_verdict: "reject", critic_feedback: "Очень мало источников, websites отсутствуют, what_they_do из догадок. Forced submit после 3 попыток.",
    turns: 18, elapsed_s: 612.4, tokens: { main: { prompt: 91230, completion: 4120, last_prompt: 12440 }, aux: { prompt: 2340, completion: 540 }, grand_total: 98230 },
    tool_call_counts: { web_serp: 15, web_scrape: 9, submit_org_card: 3 }, refraser_runs: 2, submit_attempts: 3, compactions: 1, forced_submit: true, blocked_domains: ["rusprofile.ru", "spark-interfax.ru"], review_status: "flagged",
    card: {
      what_they_do: "Оптовые поставки промышленного оборудования (по данным yandex maps). Подробной информации в открытых источниках не найдено.",
      scale_indicators: [], tech_stack: [], vacancies: [],
      social: { vk: [], telegram: [], instagram: [], youtube: [], linkedin: [], habr: [] },
      contacts: { phones: [{ number: "+7 (812) 318-22-11", context: "Яндекс.Карты" }], emails: [], websites: [] },
      yandex_maps: { rating: 3.2, reviews_count: 4, reviews_sample: ["Так и не дозвонился", "Долго отвечают"], hours: "" },
      problems_signals: ["Нет публичного сайта", "Низкий рейтинг yandex.maps", "Нет открытых вакансий"],
      sources: [
        { url: "https://yandex.ru/maps/org/1338920147", what_it_provided: "телефон, адрес, рейтинг" },
        { url: "https://2gis.ru/spb/firm/70000001028841234", what_it_provided: "категория, часы работы" },
      ],
    },
    queries_history: ["ООО Промтехресурс СПб", "Промтехресурс Лиговский 87", "Промтехресурс сайт", "Промтехресурс снабжение", "Промтехресурс ИНН"], visited_urls: ["https://yandex.ru/maps/org/1338920147", "https://2gis.ru/spb/firm/70000001028841234"],
    trace: [], critic_events: [
      { turn: 8, role: "critic", score: 3.2, verdict: "reject", missing: ["websites", "what_they_do", "scale_indicators"], wrong: [], feedback: "Карточка слишком скудная." },
      { turn: 14, role: "critic", score: 4.1, verdict: "reject", missing: ["websites", "scale_indicators"], wrong: [], feedback: "Всё ещё слабо." },
      { turn: 18, role: "critic", score: 4.5, verdict: "reject", missing: ["websites"], wrong: [], feedback: "После 3 попыток force-accept. Реально мало публичной информации." },
    ],
  },

  // Mid-score restaurant
  {
    oid: "1112480199", model_key: "local", name: "Кафе Утка",
    anchor: { name: "Кафе Утка", oid: "1112480199", address: "Санкт-Петербург, ул. Рубинштейна, 24", city: "Санкт-Петербург", categories: ["Кафе", "европейская кухня"], yandex_phones: ["+7 (812) 612-44-71"], yandex_site: "https://utka.spb", yandex_url: "https://yandex.ru/maps/org/1112480199" },
    critic_score: 7.8, critic_verdict: "pass", critic_feedback: "Хорошая карточка, отсутствует tech_stack (норм для общепита).",
    turns: 8, elapsed_s: 248.2, tokens: { main: { prompt: 38420, completion: 2240, last_prompt: 6420 }, aux: { prompt: 820, completion: 280 }, grand_total: 41760 },
    tool_call_counts: { web_serp: 7, web_scrape: 11, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "edited",
    card: {
      what_they_do: "Авторское кафе на ул. Рубинштейна с акцентом на блюда из утки. Работает с 2019 года. Бранч-меню, винная карта, периодически — гастро-ужины.",
      scale_indicators: ["~25 посадочных мест", "Средний чек 1800 ₽", "Резерв через TheFork и Resto.ru"],
      tech_stack: [],
      vacancies: [{ title: "Официант", url: "https://hh.ru/vacancy/91002211", platform: "hh.ru" }],
      social: { vk: ["https://vk.com/utka.spb"], telegram: ["https://t.me/utka_spb"], instagram: ["https://instagram.com/utka.spb"], youtube: [], linkedin: [], habr: [] },
      contacts: { phones: [{ number: "+7 (812) 612-44-71", context: "сайт, бронь" }], emails: [{ address: "hi@utka.spb", context: "сайт" }], websites: ["https://utka.spb"] },
      yandex_maps: { rating: 4.7, reviews_count: 312, reviews_sample: ["Лучшая утка в городе", "Уютная атмосфера, винная карта"], hours: "Ср-Вс 12:00-23:00" },
      problems_signals: [],
      sources: [
        { url: "https://utka.spb", what_it_provided: "меню, контакты, концепция" },
        { url: "https://www.afisha.ru/restaurant/12892/", what_it_provided: "отзывы критиков, средний чек" },
      ],
    },
    queries_history: ["Кафе Утка Рубинштейна", "Утка кафе СПб меню"], visited_urls: ["https://utka.spb", "https://www.afisha.ru/restaurant/12892/"], trace: [],
    critic_events: [{ turn: 8, role: "critic", score: 7.8, verdict: "pass", missing: ["tech_stack"], wrong: [], feedback: "Хорошая карточка." }],
  },

  // Empty what_they_do
  {
    oid: "1772019388", model_key: "local", name: "Магазин Гранд",
    anchor: { name: "Магазин Гранд", oid: "1772019388", address: "Санкт-Петербург, Богатырский пр., 18", city: "Санкт-Петербург", categories: ["Хозтовары"], yandex_phones: [], yandex_site: null, yandex_url: "https://yandex.ru/maps/org/1772019388" },
    critic_score: 3.1, critic_verdict: "reject", critic_feedback: "what_they_do пустое. Реально не нашли публичной информации.",
    turns: 22, elapsed_s: 712.1, tokens: { main: { prompt: 102310, completion: 4980, last_prompt: 13280 }, aux: { prompt: 2890, completion: 720 }, grand_total: 110900 },
    tool_call_counts: { web_serp: 19, web_scrape: 12, submit_org_card: 3 }, refraser_runs: 3, submit_attempts: 3, compactions: 1, forced_submit: true, blocked_domains: [], review_status: "new",
    card: {
      what_they_do: "",
      scale_indicators: [], tech_stack: [], vacancies: [],
      social: { vk: [], telegram: [], instagram: [], youtube: [], linkedin: [], habr: [] },
      contacts: { phones: [], emails: [], websites: [] },
      yandex_maps: { rating: 0, reviews_count: 0, reviews_sample: [], hours: "" },
      problems_signals: ["Нет публичных контактов", "Нет сайта", "Нет отзывов"],
      sources: [{ url: "https://yandex.ru/maps/org/1772019388", what_it_provided: "только название и адрес" }],
    },
    queries_history: ["Магазин Гранд Богатырский 18", "Гранд хозтовары СПб"], visited_urls: ["https://yandex.ru/maps/org/1772019388"], trace: [],
    critic_events: [
      { turn: 22, role: "critic", score: 3.1, verdict: "reject", missing: ["what_they_do", "websites", "phones"], wrong: [], feedback: "Слишком мало данных. Force-accept." },
    ],
  },

  // Hospitality clinic
  {
    oid: "1281901022", model_key: "local", name: "Стоматология Аврора Дент",
    anchor: { name: "Стоматология Аврора Дент", oid: "1281901022", address: "Санкт-Петербург, Большой пр. П.С., 76", city: "Санкт-Петербург", categories: ["Стоматология", "медицинская клиника"], yandex_phones: ["+7 (812) 232-19-04", "+7 (812) 232-19-05"], yandex_site: "https://aurora-dent.ru", yandex_url: "https://yandex.ru/maps/org/1281901022" },
    critic_score: 8.6, critic_verdict: "pass", critic_feedback: "Хорошие источники, есть лицензии и врачи.",
    turns: 11, elapsed_s: 384.2, tokens: { main: { prompt: 58410, completion: 3120, last_prompt: 8920 }, aux: { prompt: 1180, completion: 380 }, grand_total: 63090 },
    tool_call_counts: { web_serp: 10, web_scrape: 16, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "new",
    card: {
      what_they_do: "Сеть стоматологических клиник «Аврора Дент». Терапия, имплантология, ортодонтия, детская стоматология. Открыты с 2008 года, 3 филиала в СПб.",
      scale_indicators: ["3 филиала", "~60 сотрудников", "Лицензия Росздравнадзора с 2008"],
      tech_stack: ["1С: Медицина", "MyDent (IT-система)"],
      vacancies: [
        { title: "Врач-стоматолог терапевт", url: "https://hh.ru/vacancy/91728801", platform: "hh.ru" },
        { title: "Ассистент стоматолога", url: "https://hh.ru/vacancy/91728802", platform: "hh.ru" },
      ],
      social: { vk: ["https://vk.com/aurora_dent"], telegram: ["https://t.me/aurora_dent_clinic"], instagram: [], youtube: [], linkedin: [], habr: [] },
      contacts: { phones: [{ number: "+7 (812) 232-19-04", context: "регистратура" }, { number: "+7 (812) 232-19-05", context: "филиал П.С." }], emails: [{ address: "info@aurora-dent.ru", context: "сайт" }], websites: ["https://aurora-dent.ru"] },
      yandex_maps: { rating: 4.6, reviews_count: 184, reviews_sample: ["Профессиональная команда, чисто", "Дорого, но качественно"], hours: "Пн-Сб 9:00-21:00" },
      problems_signals: [],
      sources: [
        { url: "https://aurora-dent.ru", what_it_provided: "услуги, врачи, цены" },
        { url: "https://www.napopravku.ru/spb/clinics/avrora-dent/", what_it_provided: "отзывы пациентов" },
        { url: "https://prodoctorov.ru/spb/lpu/aurora-dent/", what_it_provided: "лицензии, врачи" },
      ],
    },
    queries_history: ["Аврора Дент СПб", "Аврора Дент филиалы", "Аврора Дент лицензия"], visited_urls: ["https://aurora-dent.ru", "https://www.napopravku.ru/spb/clinics/avrora-dent/"], trace: [],
    critic_events: [{ turn: 11, role: "critic", score: 8.6, verdict: "pass", missing: [], wrong: [], feedback: "Хорошие источники." }],
  },

  // More variations (shorter)
  { oid: "1929847711", model_key: "local", name: "Барбершоп Топор", anchor: { name: "Барбершоп Топор", oid: "1929847711", address: "Санкт-Петербург, ул. Жуковского, 41", city: "Санкт-Петербург", categories: ["Барбершоп"], yandex_phones: ["+7 (812) 244-89-04"], yandex_site: "https://topor.barber", yandex_url: "" }, critic_score: 8.2, critic_verdict: "pass", critic_feedback: "OK.", turns: 7, elapsed_s: 198.4, tokens: { main: { prompt: 32100, completion: 1980, last_prompt: 5840 }, aux: { prompt: 720, completion: 240 }, grand_total: 35040 }, tool_call_counts: { web_serp: 6, web_scrape: 8, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "reviewed",
    card: { what_they_do: "Сетка барбершопов «Топор», 4 филиала по СПб.", scale_indicators: ["4 филиала"], tech_stack: [], vacancies: [], social: { vk: ["https://vk.com/topor_barber"], telegram: ["https://t.me/topor_barber"], instagram: [], youtube: [], linkedin: [], habr: [] }, contacts: { phones: [{ number: "+7 (812) 244-89-04", context: "сайт" }], emails: [], websites: ["https://topor.barber"] }, yandex_maps: { rating: 4.9, reviews_count: 89, reviews_sample: [], hours: "10-22" }, problems_signals: [], sources: [{ url: "https://topor.barber", what_it_provided: "услуги" }] }, queries_history: ["Топор барбершоп"], visited_urls: [], trace: [], critic_events: [{ turn: 7, score: 8.2, verdict: "pass", missing: [], wrong: [], feedback: "OK" }] },

  { oid: "1003344891", model_key: "local", name: "ООО Криогенмаш-Сервис", anchor: { name: "ООО Криогенмаш-Сервис", oid: "1003344891", address: "Санкт-Петербург, ш. Революции, 84", city: "Санкт-Петербург", categories: ["Промышленное оборудование", "обслуживание"], yandex_phones: ["+7 (812) 449-11-22"], yandex_site: null, yandex_url: "" }, critic_score: 6.8, critic_verdict: "pass", critic_feedback: "Усреднённая карточка B2B.", turns: 14, elapsed_s: 488.1, tokens: { main: { prompt: 71200, completion: 3210, last_prompt: 9840 }, aux: { prompt: 1420, completion: 440 }, grand_total: 76270 }, tool_call_counts: { web_serp: 12, web_scrape: 14, submit_org_card: 2 }, refraser_runs: 1, submit_attempts: 2, compactions: 1, forced_submit: false, blocked_domains: [], review_status: "new",
    card: { what_they_do: "Обслуживание криогенного оборудования, поставки запчастей для промышленных газовых установок.", scale_indicators: ["~30 сотрудников"], tech_stack: [], vacancies: [{ title: "Инженер-механик", url: "https://hh.ru/vacancy/91002298", platform: "hh.ru" }], social: { vk: [], telegram: [], instagram: [], youtube: [], linkedin: [], habr: [] }, contacts: { phones: [{ number: "+7 (812) 449-11-22", context: "yandex" }], emails: [{ address: "info@cryo-service.ru", context: "rusprofile" }], websites: ["https://cryo-service.ru"] }, yandex_maps: { rating: 4.2, reviews_count: 8, reviews_sample: [], hours: "" }, problems_signals: ["Маленькое онлайн-присутствие"], sources: [{ url: "https://rusprofile.ru/id/2842819", what_it_provided: "юр. данные" }, { url: "https://cryo-service.ru", what_it_provided: "услуги" }] }, queries_history: ["Криогенмаш-Сервис"], visited_urls: [], trace: [], critic_events: [{ turn: 14, score: 6.8, verdict: "pass", missing: ["social"], wrong: [], feedback: "Слабая социалка." }] },

  { oid: "1556728199", model_key: "local", name: "Школа танцев Pulse", anchor: { name: "Школа танцев Pulse", oid: "1556728199", address: "Санкт-Петербург, Невский пр., 130", city: "Санкт-Петербург", categories: ["Танцевальная школа"], yandex_phones: ["+7 (981) 700-12-34"], yandex_site: "https://pulse.dance", yandex_url: "" }, critic_score: 9.1, critic_verdict: "pass", critic_feedback: "Полная карточка.", turns: 9, elapsed_s: 287.4, tokens: { main: { prompt: 44210, completion: 2640, last_prompt: 7140 }, aux: { prompt: 920, completion: 320 }, grand_total: 48090 }, tool_call_counts: { web_serp: 8, web_scrape: 12, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "new",
    card: { what_they_do: "Школа современного танца Pulse — хип-хоп, контемпорари, джаз-фанк. Дети и взрослые, 2 студии.", scale_indicators: ["~20 преподавателей", "Открыта в 2017"], tech_stack: [], vacancies: [], social: { vk: ["https://vk.com/pulse_dance"], telegram: ["https://t.me/pulse_dance"], instagram: ["https://instagram.com/pulse.dance"], youtube: ["https://youtube.com/@pulsedance"], linkedin: [], habr: [] }, contacts: { phones: [{ number: "+7 (981) 700-12-34", context: "сайт" }], emails: [{ address: "info@pulse.dance", context: "сайт" }], websites: ["https://pulse.dance"] }, yandex_maps: { rating: 4.9, reviews_count: 156, reviews_sample: ["Лучшие преподаватели"], hours: "Пн-Вс 10-22" }, problems_signals: [], sources: [{ url: "https://pulse.dance", what_it_provided: "вся карточка" }] }, queries_history: ["Pulse школа танцев"], visited_urls: [], trace: [], critic_events: [{ turn: 9, score: 9.1, verdict: "pass", missing: [], wrong: [], feedback: "Полная карточка." }] },

  { oid: "1844810098", model_key: "local", name: "Автосервис Спецтех", anchor: { name: "Автосервис Спецтех", oid: "1844810098", address: "Санкт-Петербург, Софийская ул., 8", city: "Санкт-Петербург", categories: ["Автосервис"], yandex_phones: ["+7 (812) 921-44-55"], yandex_site: null, yandex_url: "" }, critic_score: 5.8, critic_verdict: "reject", critic_feedback: "Мало источников, нет сайта.", turns: 16, elapsed_s: 522.3, tokens: { main: { prompt: 79800, completion: 3680, last_prompt: 11200 }, aux: { prompt: 1820, completion: 540 }, grand_total: 85840 }, tool_call_counts: { web_serp: 14, web_scrape: 11, submit_org_card: 2 }, refraser_runs: 2, submit_attempts: 2, compactions: 0, forced_submit: false, blocked_domains: ["avtoservis-spectech.spb.ru"], review_status: "flagged",
    card: { what_they_do: "Автосервис, специализация на коммерческом транспорте.", scale_indicators: [], tech_stack: [], vacancies: [], social: { vk: [], telegram: [], instagram: [], youtube: [], linkedin: [], habr: [] }, contacts: { phones: [{ number: "+7 (812) 921-44-55", context: "yandex" }], emails: [], websites: [] }, yandex_maps: { rating: 3.8, reviews_count: 12, reviews_sample: [], hours: "" }, problems_signals: ["Сайт недоступен", "Низкий рейтинг"], sources: [{ url: "https://yandex.ru/maps/org/1844810098", what_it_provided: "телефон" }] }, queries_history: ["Спецтех автосервис"], visited_urls: [], trace: [], critic_events: [{ turn: 16, score: 5.8, verdict: "reject", missing: ["websites", "scale_indicators"], wrong: [], feedback: "Мало данных." }] },

  { oid: "1721044567", model_key: "local", name: "Книжный клуб «Подписка»", anchor: { name: "Книжный клуб «Подписка»", oid: "1721044567", address: "Санкт-Петербург, ул. Большая Морская, 18", city: "Санкт-Петербург", categories: ["Книжный магазин", "лекторий"], yandex_phones: ["+7 (812) 314-12-12"], yandex_site: "https://podpiska.club", yandex_url: "" }, critic_score: 8.9, critic_verdict: "pass", critic_feedback: "Хорошо.", turns: 8, elapsed_s: 244.5, tokens: { main: { prompt: 39200, completion: 2340, last_prompt: 6440 }, aux: { prompt: 820, completion: 280 }, grand_total: 42640 }, tool_call_counts: { web_serp: 7, web_scrape: 10, submit_org_card: 1 }, refraser_runs: 0, submit_attempts: 1, compactions: 0, forced_submit: false, blocked_domains: [], review_status: "new",
    card: { what_they_do: "Книжный клуб «Подписка» — независимый книжный магазин и лекторий на Большой Морской. Кураторские полки, литературные встречи раз в неделю.", scale_indicators: ["3 куратора", "Открыт 2016"], tech_stack: [], vacancies: [], social: { vk: ["https://vk.com/podpiska_club"], telegram: ["https://t.me/podpiska_club"], instagram: [], youtube: [], linkedin: [], habr: [] }, contacts: { phones: [{ number: "+7 (812) 314-12-12", context: "сайт" }], emails: [{ address: "hi@podpiska.club", context: "сайт" }], websites: ["https://podpiska.club"] }, yandex_maps: { rating: 4.9, reviews_count: 78, reviews_sample: ["Очень уютно"], hours: "Пн-Вс 11-21" }, problems_signals: [], sources: [{ url: "https://podpiska.club", what_it_provided: "услуги, мероприятия" }] }, queries_history: ["Подписка книжный СПб"], visited_urls: [], trace: [], critic_events: [{ turn: 8, score: 8.9, verdict: "pass", missing: [], wrong: [], feedback: "Хорошо." }] },

  { oid: "1188273400", model_key: "local", name: "ИП Иванов А.С.", anchor: { name: "ИП Иванов А.С.", oid: "1188273400", address: "Санкт-Петербург, ул. Звёздная, 12", city: "Санкт-Петербург", categories: ["Бытовые услуги"], yandex_phones: [], yandex_site: null, yandex_url: "" }, critic_score: 2.4, critic_verdict: "reject", critic_feedback: "Карточка пустая, информации в публичных источниках нет.", turns: 24, elapsed_s: 798.4, tokens: { main: { prompt: 118200, completion: 5240, last_prompt: 14820 }, aux: { prompt: 3120, completion: 820 }, grand_total: 127380 }, tool_call_counts: { web_serp: 22, web_scrape: 14, submit_org_card: 3 }, refraser_runs: 4, submit_attempts: 3, compactions: 2, forced_submit: true, blocked_domains: [], review_status: "new",
    card: { what_they_do: "", scale_indicators: [], tech_stack: [], vacancies: [], social: { vk: [], telegram: [], instagram: [], youtube: [], linkedin: [], habr: [] }, contacts: { phones: [], emails: [], websites: [] }, yandex_maps: { rating: 0, reviews_count: 0, reviews_sample: [], hours: "" }, problems_signals: ["Нет публичной информации"], sources: [{ url: "https://yandex.ru/maps/org/1188273400", what_it_provided: "только название" }] }, queries_history: ["ИП Иванов СПб бытовые услуги"], visited_urls: [], trace: [], critic_events: [{ turn: 24, score: 2.4, verdict: "reject", missing: ["everything"], wrong: [], feedback: "Force-accept, реально пусто." }] },
];

window.MOCK_CARDS = MOCK_CARDS;
window.FREMM_CARD = FREMM_CARD;
