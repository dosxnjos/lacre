// Hands-on tests the buyer does on the iPhone itself. Text lives here (pt-BR and en)
// so the list can be reviewed in one place. Results are kept in the session state
// and included in the exported report.
import type { Lang } from "./types";

export type L10n = Record<Lang, string>;

export interface CheckGroup { id: string; title: L10n; note?: L10n }

export interface CheckItem {
  id: string;
  group: string;
  title: L10n;
  /** How to test, one step per entry. */
  how: L10n[];
  /** Shows the touch-test QR code next to this item. */
  touchPage?: boolean;
  /** Marks the items that most often hide a scam. */
  key?: boolean;
}

export const TOUCH_TEST_URL = "https://dosxnjos.github.io/lacre/touch-test/";

export const GROUPS: CheckGroup[] = [
  { id: "identity", title: { "pt-BR": "Identidade e travas", en: "Identity and locks" } },
  {
    id: "screen",
    title: { "pt-BR": "Tela e toque", en: "Screen and touch" },
    note: {
      "pt-BR": "É aqui que mais se esconde tela paralela. Faça com calma e na tomada.",
      en: "This is where aftermarket screens hide most often. Take your time, and test plugged into the wall.",
    },
  },
  { id: "sensors", title: { "pt-BR": "Sensores e Face ID", en: "Sensors and Face ID" } },
  { id: "cameras", title: { "pt-BR": "Câmeras", en: "Cameras" } },
  { id: "audio", title: { "pt-BR": "Som e microfones", en: "Sound and microphones" } },
  { id: "buttons", title: { "pt-BR": "Botões e vibração", en: "Buttons and vibration" } },
  { id: "connectivity", title: { "pt-BR": "Conexões", en: "Connections" } },
  { id: "charging", title: { "pt-BR": "Carregamento", en: "Charging" } },
  { id: "body", title: { "pt-BR": "Corpo e sinais de abertura", en: "Body and signs of opening" } },
];

export const CHECKLIST: CheckItem[] = [
  // ---- identity and locks
  {
    id: "imei", group: "identity", key: true,
    title: { "pt-BR": "IMEI: disque *#06#", en: "IMEI: dial *#06#" },
    how: [
      { "pt-BR": "No app Telefone, digite *#06#. O IMEI aparece na hora (dois, se tiver eSIM ou chip duplo).", en: "In the Phone app, type *#06#. The IMEI shows up right away (two if it has eSIM or dual SIM)." },
      { "pt-BR": "Tem que ser igual ao de Ajustes > Geral > Sobre, ao da caixa e ao da nota fiscal.", en: "It must match Settings > General > About, the box and the receipt." },
      { "pt-BR": "Consulte cada IMEI na lista oficial de bloqueio (no Brasil: Anatel, “situação do celular”, ou consultaaparelhoimpedido.com.br). Sites de IMEI de terceiros não valem.", en: "Look up every IMEI on the official blocklist for your country (in Brazil: Anatel “situação do celular”; elsewhere, your carrier or the national registry). Third-party IMEI sites don't count." },
    ],
  },
  {
    id: "parts_history", group: "identity", key: true,
    title: { "pt-BR": "Histórico de Peças e Serviço", en: "Parts and Service History" },
    how: [
      { "pt-BR": "Ajustes > Geral > Sobre, role até Histórico de Peças e Serviço. Se a seção não aparece, nenhuma peça rastreada neste modelo foi registrada como trocada.", en: "Settings > General > About, scroll to Parts and Service History. If the section isn't there, no part tracked on this model was recorded as replaced." },
      { "pt-BR": "“Genuína” = trocada por peça Apple. “Desconhecida” = peça paralela ou não verificada. “Usada” = peça Apple vinda de outro iPhone.", en: "“Genuine” = replaced with an Apple part. “Unknown” = aftermarket or unverified part. “Used” = an Apple part taken from another iPhone." },
    ],
  },
  {
    id: "battery_screen", group: "identity",
    title: { "pt-BR": "Tela de Saúde da Bateria", en: "Battery Health screen" },
    how: [
      { "pt-BR": "Ajustes > Bateria > Saúde da Bateria. Tem que mostrar a porcentagem, e não a mensagem de que não foi possível verificar se a bateria é genuína.", en: "Settings > Battery > Battery Health. It must show a percentage, not the message that it can't verify the battery is genuine." },
      { "pt-BR": "Abaixo de 80% a bateria pede troca: considere no preço. Do iPhone 15 em diante, a mesma tela mostra a data de fabricação e de primeiro uso.", en: "Below 80% the battery needs replacing: count it in the price. From iPhone 15 on, the same screen shows the manufacture and first-use dates." },
    ],
  },
  {
    id: "findmy_erase", group: "identity", key: true,
    title: { "pt-BR": "Buscar desligado, sair do iCloud e apagar na sua frente", en: "Find My off, sign out of iCloud and erase in front of you" },
    how: [
      { "pt-BR": "O vendedor desliga o Buscar e sai da conta: Ajustes > nome dele > Sair (pede a senha da conta Apple dele).", en: "The seller turns off Find My and signs out: Settings > their name > Sign Out (it asks for their Apple Account password)." },
      { "pt-BR": "Depois apaga tudo: Ajustes > Geral > Transferir ou Redefinir > Apagar Conteúdo e Ajustes.", en: "Then erases everything: Settings > General > Transfer or Reset > Erase All Content and Settings." },
      { "pt-BR": "Configure com a sua conta antes de pagar. Se pedir a conta de outra pessoa na ativação, não compre.", en: "Set it up with your own account before paying. If activation asks for someone else's account, don't buy it." },
    ],
  },

  // ---- screen and touch
  {
    id: "touch_calibration", group: "screen", key: true, touchPage: true,
    title: { "pt-BR": "Toque calibrado: cai exatamente embaixo do dedo", en: "Touch calibration: lands exactly under your finger" },
    how: [
      { "pt-BR": "Abra a página de teste de toque (QR ao lado) ou o Notas com um desenho. Toque devagar em vários pontos, cantos e bordas.", en: "Open the touch test page (QR code nearby) or a drawing in Notes. Tap slowly in many spots, corners and edges." },
      { "pt-BR": "A mira (ou o traço) tem que ficar bem embaixo do dedo. Toque registrado um pouco abaixo ou ao lado do dedo é sinal de tela paralela: alerta vermelho.", en: "The crosshair (or the line) must sit right under your finger. A touch registered a little below or beside your finger is a sign of an aftermarket screen: a red flag." },
    ],
  },
  {
    id: "ghost_touch_wall", group: "screen", key: true, touchPage: true,
    title: { "pt-BR": "Toque fantasma ou maluco carregando na tomada", en: "Ghost or erratic touch while charging from a wall outlet" },
    how: [
      { "pt-BR": "Leve um carregador de tomada comum. Power bank não basta: a corrente dele é limpa e pode esconder o defeito típico de tela paralela.", en: "Bring a regular wall charger. A power bank isn't enough: its current is clean and can hide the defect typical of aftermarket screens." },
      { "pt-BR": "Teste primeiro fora da tomada e depois ligado na tomada, uns 2 minutos cada.", en: "Test unplugged first, then plugged into the wall, about 2 minutes each." },
      { "pt-BR": "Role o feed de um app como o Instagram, abra e feche coisas e digite no teclado, principalmente as teclas das bordas (Q, P, A, L, apagar).", en: "Scroll through an app like Instagram, open and close things and type on the keyboard, especially the edge keys (Q, P, A, L, delete)." },
      { "pt-BR": "Problema: toque que pula para todo lado, abre coisas sozinho, cai fora do lugar ou fica impreciso só na tomada.", en: "Problem: touches jumping around, things opening by themselves, touches landing in the wrong place or getting imprecise only while plugged in." },
    ],
  },
  {
    id: "touch_coverage", group: "screen", touchPage: true,
    title: { "pt-BR": "Toque na tela inteira", en: "Touch across the whole screen" },
    how: [
      { "pt-BR": "Na página de teste, passe o dedo até preencher toda a grade, incluindo cantos e as bordas de cima e de baixo.", en: "On the test page, drag your finger until the whole grid is filled, including corners and the top and bottom edges." },
      { "pt-BR": "Sem página: segure um ícone da tela de início e arraste por toda a tela. Ele não pode “soltar” no meio do caminho.", en: "Without the page: hold an app icon on the Home Screen and drag it around the whole screen. It must not drop halfway." },
    ],
  },
  {
    id: "dead_pixels", group: "screen", touchPage: true,
    title: { "pt-BR": "Pixels mortos, manchas e brilho irregular", en: "Dead pixels, stains and uneven brightness" },
    how: [
      { "pt-BR": "Mostre cores sólidas em tela cheia (a página de teste tem; ou abra imagens brancas, pretas, vermelhas, verdes e azuis) com o brilho no máximo.", en: "Show solid full-screen colors (the test page has them, or open plain white, black, red, green and blue images) at full brightness." },
      { "pt-BR": "Procure pontos, manchas amareladas, sombras nas bordas e linhas. No preto, a tela OLED tem que ficar totalmente apagada.", en: "Look for dots, yellowish patches, shadows on the edges and lines. On black, an OLED screen must look fully off." },
    ],
  },
  {
    id: "true_tone", group: "screen", key: true,
    title: { "pt-BR": "True Tone aparece na Central de Controle", en: "True Tone shows up in Control Center" },
    how: [
      { "pt-BR": "Abra a Central de Controle, segure o controle de brilho: o botão True Tone tem que estar lá e funcionar (a tela fica mais quente ou mais fria).", en: "Open Control Center and hold the brightness control: the True Tone button must be there and work (the screen turns warmer or cooler)." },
      { "pt-BR": "Sem o botão de True Tone = tela trocada sem transferir a calibração.", en: "No True Tone button = the screen was replaced without transferring its calibration." },
    ],
  },
  {
    id: "brightness", group: "screen",
    title: { "pt-BR": "Brilho e brilho automático", en: "Brightness and auto-brightness" },
    how: [
      { "pt-BR": "Arraste o brilho do mínimo ao máximo: tem que mudar suave, sem piscar.", en: "Drag brightness from minimum to maximum: it must change smoothly, without flicker." },
      { "pt-BR": "Com o brilho automático ligado (Ajustes > Acessibilidade > Tela e Tamanho do Texto), cubra a parte de cima da tela com a mão: o brilho deve baixar em alguns segundos. Isso testa o sensor de luz.", en: "With auto-brightness on (Settings > Accessibility > Display & Text Size), cover the top of the screen with your hand: brightness should drop within a few seconds. This tests the light sensor." },
    ],
  },

  // ---- sensors and biometrics
  {
    id: "proximity", group: "sensors",
    title: { "pt-BR": "Sensor de proximidade", en: "Proximity sensor" },
    how: [
      { "pt-BR": "Faça uma ligação e encoste o iPhone na orelha (ou cubra a parte de cima com a mão): a tela tem que apagar e voltar quando afastar.", en: "Make a call and hold the iPhone to your ear (or cover the top with your hand): the screen must turn off and come back when you move it away." },
    ],
  },
  {
    id: "biometrics", group: "sensors", key: true,
    title: { "pt-BR": "Face ID ou Touch ID", en: "Face ID or Touch ID" },
    how: [
      { "pt-BR": "Ajustes > Face ID e Código (ou Touch ID e Código): cadastre o seu rosto ou dedo até o fim e depois desbloqueie com ele.", en: "Settings > Face ID & Passcode (or Touch ID & Passcode): enroll your face or finger all the way, then unlock with it." },
      { "pt-BR": "Se a opção não aparecer ou der erro no cadastro, o sensor foi trocado ou está com defeito.", en: "If the option is missing or enrollment fails, the sensor was replaced or is faulty." },
    ],
  },
  {
    id: "compass", group: "sensors",
    title: { "pt-BR": "Bússola e giroscópio", en: "Compass and gyroscope" },
    how: [
      { "pt-BR": "Abra o app Bússola e gire o corpo: o norte acompanha. Deite o iPhone e use o Nível (no app Medida): a bolha responde.", en: "Open the Compass app and turn around: north follows. Lay the iPhone flat and use Level (in the Measure app): the bubble responds." },
      { "pt-BR": "Gire o iPhone de pé para deitado num vídeo: a imagem tem que girar junto.", en: "Rotate the iPhone from portrait to landscape while playing a video: the picture must rotate too." },
    ],
  },

  // ---- cameras
  {
    id: "cameras_all", group: "cameras", key: true,
    title: { "pt-BR": "Todas as câmeras traseiras e a frontal", en: "Every rear camera and the front camera" },
    how: [
      { "pt-BR": "No app Câmera, passe por 0,5×, 1× e 2×/3×/5× (conforme o modelo) e vire para a frontal. Cada uma tem que abrir sem tela preta nem tremor.", en: "In the Camera app, switch between 0.5×, 1× and 2×/3×/5× (depending on the model) and flip to the front camera. Each must open without a black screen or shaking." },
      { "pt-BR": "Tire uma foto em cada uma e confira manchas, poeira ou pontos na imagem.", en: "Take a photo with each and look for spots, dust or dots in the picture." },
    ],
  },
  {
    id: "camera_focus", group: "cameras",
    title: { "pt-BR": "Foco e estabilização", en: "Focus and stabilization" },
    how: [
      { "pt-BR": "Aproxime de um texto a uns 10 cm e toque nele: tem que focar nítido. A imagem não pode tremer nem fazer barulho de “chacoalho” com o iPhone parado.", en: "Bring it to some text about 10 cm away and tap it: it must focus sharply. The image must not shake or rattle while the iPhone is still." },
    ],
  },
  {
    id: "flash", group: "cameras",
    title: { "pt-BR": "Flash e lanterna", en: "Flash and flashlight" },
    how: [
      { "pt-BR": "Ligue a lanterna pela Central de Controle e tire uma foto com flash ligado.", en: "Turn on the flashlight from Control Center and take a photo with the flash on." },
    ],
  },
  {
    id: "video", group: "cameras",
    title: { "pt-BR": "Gravação de vídeo", en: "Video recording" },
    how: [
      { "pt-BR": "Grave uns 10 segundos de vídeo com a traseira e com a frontal, falando, e assista: imagem e som têm que estar normais.", en: "Record about 10 seconds of video with the rear and the front cameras while talking, then play it back: picture and sound must be normal." },
    ],
  },

  // ---- audio
  {
    id: "mics", group: "audio", key: true,
    title: { "pt-BR": "Os 3 microfones", en: "The 3 microphones" },
    how: [
      { "pt-BR": "Microfone de baixo: grave um áudio no Gravador e ouça.", en: "Bottom mic: record a voice memo and play it back." },
      { "pt-BR": "Microfone da frente: grave um vídeo com a câmera frontal falando.", en: "Front mic: record a front-camera video while talking." },
      { "pt-BR": "Microfone de trás: grave um vídeo com a câmera traseira falando.", en: "Rear mic: record a rear-camera video while talking." },
      { "pt-BR": "Em cada um, a voz tem que sair clara, sem chiado nem volume baixo demais.", en: "In each, the voice must come out clear, without hiss or very low volume." },
    ],
  },
  {
    id: "call", group: "audio", key: true,
    title: { "pt-BR": "Ligação de voz", en: "Phone call" },
    how: [
      { "pt-BR": "Ligue para alguém (ou para o seu número): você tem que ouvir pelo alto-falante de cima e a outra pessoa tem que te ouvir bem. Teste também no viva-voz.", en: "Call someone (or your own number): you must hear through the top earpiece and the other person must hear you well. Try speakerphone too." },
    ],
  },
  {
    id: "speakers", group: "audio",
    title: { "pt-BR": "Os dois alto-falantes", en: "Both speakers" },
    how: [
      { "pt-BR": "Toque uma música no volume máximo: o som tem que sair de baixo e de cima, sem chiar nem estourar.", en: "Play music at full volume: sound must come from both the bottom and the top, without crackling or distortion." },
      { "pt-BR": "Alto-falante de cima (auricular): numa ligação, ou tocando um áudio do Gravador com o iPhone na orelha.", en: "Top speaker (earpiece): during a call, or playing a voice memo with the iPhone held to your ear." },
    ],
  },

  // ---- buttons and haptics
  {
    id: "buttons", group: "buttons",
    title: { "pt-BR": "Todos os botões", en: "Every button" },
    how: [
      { "pt-BR": "Volume +, volume − e botão lateral: cada um tem que dar um clique firme e responder na hora. Controle da Câmera também, se o modelo tiver.", en: "Volume up, volume down and the side button: each must click firmly and respond right away. The Camera Control too, if the model has one." },
    ],
  },
  {
    id: "silent_switch", group: "buttons",
    title: { "pt-BR": "Chave de silêncio ou botão de Ação", en: "Ring/Silent switch or Action button" },
    how: [
      { "pt-BR": "Mude a chave (ou segure o botão de Ação): o aviso de silencioso tem que aparecer na tela e o iPhone vibra.", en: "Flip the switch (or hold the Action button): the silent mode banner must appear and the iPhone vibrates." },
    ],
  },
  {
    id: "vibration", group: "buttons",
    title: { "pt-BR": "Vibração e resposta do teclado", en: "Vibration and keyboard haptics" },
    how: [
      { "pt-BR": "Ligue Ajustes > Sons e Tátil > Retorno do Teclado > Tátil e digite: cada tecla dá uma batidinha. Ao receber uma ligação, ele tem que vibrar forte e sem barulho de peça solta.", en: "Turn on Settings > Sounds & Haptics > Keyboard Feedback > Haptic and type: each key gives a little tap. On an incoming call it must vibrate strongly, with no loose rattle." },
    ],
  },

  // ---- connectivity
  {
    id: "wifi", group: "connectivity",
    title: { "pt-BR": "Wi-Fi", en: "Wi-Fi" },
    how: [
      { "pt-BR": "Entre numa rede Wi-Fi (o roteador do celular de alguém serve) e abra uma página no Safari. O botão de Wi-Fi não pode ficar cinza.", en: "Join a Wi-Fi network (someone's phone hotspot works) and load a page in Safari. The Wi-Fi toggle must not be greyed out." },
    ],
  },
  {
    id: "bluetooth", group: "connectivity",
    title: { "pt-BR": "Bluetooth", en: "Bluetooth" },
    how: [
      { "pt-BR": "Pareie um fone ou caixa de som Bluetooth e toque um áudio.", en: "Pair Bluetooth headphones or a speaker and play some audio." },
    ],
  },
  {
    id: "cellular", group: "connectivity", key: true,
    title: { "pt-BR": "Chip, ligação e dados móveis", en: "SIM, calls and mobile data" },
    how: [
      { "pt-BR": "Coloque o seu chip (ou ative o seu eSIM): tem que aparecer sinal da operadora. Faça uma ligação e abra uma página com o Wi-Fi desligado.", en: "Insert your SIM (or activate your eSIM): carrier signal must show up. Make a call and load a page with Wi-Fi off." },
      { "pt-BR": "“Sem serviço” com chip bom pode ser bloqueio de operadora ou IMEI bloqueado.", en: "“No Service” with a working SIM can mean a carrier lock or a blocked IMEI." },
    ],
  },
  {
    id: "gps", group: "connectivity",
    title: { "pt-BR": "GPS", en: "GPS" },
    how: [
      { "pt-BR": "Abra o Mapas e toque no botão de localização: o ponto azul tem que aparecer onde você está, com a seta apontando para onde o iPhone aponta.", en: "Open Maps and tap the location button: the blue dot must show where you are, with the beam pointing where the iPhone points." },
    ],
  },

  // ---- charging
  {
    id: "charge_cable", group: "charging",
    title: { "pt-BR": "Carregamento pelo cabo", en: "Charging by cable" },
    how: [
      { "pt-BR": "Ligue no carregador de tomada: o raio de carregando aparece na hora e não some ao mexer o cabo de leve.", en: "Plug into the wall charger: the charging bolt appears right away and doesn't drop out when you wiggle the cable gently." },
    ],
  },
  {
    id: "charge_wireless", group: "charging",
    title: { "pt-BR": "Carregamento sem fio e MagSafe", en: "Wireless and MagSafe charging" },
    how: [
      { "pt-BR": "Se tiver um carregador sem fio ou MagSafe, apoie o iPhone: tem que começar a carregar (no MagSafe, aparece a animação).", en: "If you have a wireless or MagSafe charger, place the iPhone on it: it must start charging (MagSafe shows its animation)." },
    ],
  },

  // ---- body
  {
    id: "signs_of_opening", group: "body",
    title: { "pt-BR": "Sinais de abertura", en: "Signs of opening" },
    how: [
      { "pt-BR": "Olhe a tela de lado contra a luz: não pode ter vão, cola aparente nem borda levantada entre a tela e o corpo.", en: "Look at the screen edge-on against the light: no gaps, visible glue or raised edges between screen and frame." },
      { "pt-BR": "Os parafusos ao lado do conector (modelos com Lightning) têm que ser iguais e sem marcas.", en: "The screws beside the connector (Lightning models) must match and be unmarked." },
      { "pt-BR": "Tire a gaveta do chip e olhe dentro do encaixe com uma lanterna: o indicador de líquido, quando visível, tem que ser branco ou prateado. Vermelho = contato com líquido.", en: "Remove the SIM tray and look into the slot with a flashlight: the liquid indicator, where visible, must be white or silver. Red = liquid contact." },
    ],
  },
];
