# Chiptune & Sound Design Retrô

Fontes: NES APU Sound Hardware Reference (nesdev.org), fundamentos de síntese subtrativa/FM aplicados a hardware retrô.

## 1. Canais do NES APU (Audio Processing Unit) — o vocabulário fundamental do chiptune
O NES tinha exatamente 5 canais de som, cada um com limitações específicas que DEFINEM o "som chiptune":

- **Pulse 1 e Pulse 2 (onda quadrada/pulso)**: 2 canais idênticos de onda quadrada com 4 duty cycles selecionáveis (12.5%, 25%, 50%, 75%) — o duty cycle muda o timbre (mais fino ou mais "gordo"). Usados para melodia principal e harmonia/contramelodia.
- **Triangle (onda triangular)**: timbre mais suave e "encorpado", sem controle de volume por hardware (só ligado/desligado) — tradicionalmente usado para linha de BAIXO.
- **Noise (ruído)**: gerador de ruído pseudo-aleatório com 2 modos (longo/curto período) — usado para percussão (chimbal, caixa) e efeitos de explosão/impacto.
- **DMC (Delta Modulation Channel)**: canal de sample PCM de baixa qualidade, usado com moderação (consumia CPU) para bumbo/kick ou vozes digitalizadas curtas.

Implicação de design: uma trilha chiptune autêntica de NES tem NO MÁXIMO 2 melodias simultâneas (pulse 1+2), 1 baixo (triangle) e 1 percussão (noise) — a composição precisa ser extremamente eficiente harmonicamente, sem densidade orquestral.

## 2. Diferenças de geração (NES vs SNES vs Genesis)
- **NES (1983)**: síntese "chip" pura (pulse/triangle/noise), sem sample playback real (exceto DMC limitado). Som mais "puro" e sintético.
- **SNES (1990)**: sample-based (ADPCM) com até 8 canais reais de áudio digitalizado — permite instrumentos "reais" gravados e reproduzidos, som mais orquestral (ex.: trilhas de Chrono Trigger, Secret of Mana).
- **Sega Genesis/Mega Drive (1988)**: síntese FM (chip Yamaha YM2612) com 6 canais FM + 1 canal PSG de ruído — som mais "metálico"/agressivo, característico do Sonic e jogos de ação da época.
- Escolher a "paleta sonora" retrô certa depende do mood: NES = minimalista/puro, SNES = orquestral/quente, Genesis = agressivo/FM metálico.

## 3. Envelope ADSR (Attack, Decay, Sustain, Release)
Fundamental para dar caráter a qualquer som sintetizado, incluindo chiptune:
- **Attack**: tempo até o som atingir volume máximo após o ataque da nota (curto = percussivo, longo = suave/pad).
- **Decay**: tempo de queda do volume máximo até o nível de sustain.
- **Sustain**: nível de volume mantido enquanto a nota é sustentada (não é tempo, é um nível).
- **Release**: tempo de queda do volume após a nota ser solta.
- Em chiptune, envelopes tendem a ser CURTOS e AGRESSIVOS (attack quase instantâneo, decay rápido) para simular a resposta abrupta do hardware original — softwares modernos de tracker (Famitracker, DefleMask) expõem esses parâmetros diretamente.

## 4. Arpejo de canal (técnica clássica de chiptune)
Como cada canal do NES só toca UMA nota por vez, para simular ACORDES os compositores usam arpejo rápido: alternar entre as notas do acorde em alta velocidade (16th notes ou mais rápido) dentro de um único canal, criando a ILUSÃO de polifonia ao ouvido humano.

## 5. Bitcrushing e sample rate reduction (efeitos modernos que simulam retrô)
- **Bitcrush**: reduzir a resolução de bits do áudio (ex.: de 16-bit para 4-bit) para introduzir distorção quantizada característica de hardware antigo.
- **Sample rate reduction**: reduzir a taxa de amostragem (ex.: de 44.1kHz para 8kHz) simula o aliasing e a "granulação" de hardware limitado.
- Plugins modernos (ex.: em DAWs ou via código com bibliotecas de DSP) permitem aplicar esses efeitos em samples modernos para dar caráter retrô sem depender de hardware/emuladores reais.

## 6. Ferramentas de produção chiptune modernas
- **FamiTracker / 0CC-FamiTracker**: tracker especializado em emular o NES APU com precisão, exporta para NSF (formato de música NES) ou WAV.
- **DefleMask**: tracker multi-plataforma que emula NES, Genesis, Game Boy, SMS e mais no mesmo software.
- **VSTs de chiptune** (ex.: Plogue chipsounds, Magical 8bit Plug): permitem usar timbres chiptune dentro de DAWs modernas (Ableton, FL Studio, Reaper) via MIDI, integrando com workflows de composição contemporâneos.

## 7. Aplicação em geração via código
Ao gerar áudio/MIDI programaticamente para um estilo chiptune (ver `midi-code-cookbook.md`):
- Limite-se a poucas vozes simultâneas (2-3 no máximo) para autenticidade.
- Use ondas de forma simples (square/triangle) se estiver sintetizando áudio diretamente (não apenas MIDI) via bibliotecas como `numpy`/`scipy` (síntese aditiva simples) ou `pyo`/`sounddevice` para playback.
- Quantização rítmica rígida (sem "humanização" de timing) reforça a estética de sequenciador mecânico.

## 8. Direct use with the nobu MCP

When using the nobu MCP server (see `mcp-integration.md`), the programs
`pulse_lead` and `pulse_harmony` in `add_layer` approximate NES Pulse 1/2
(melody and countermelody), and `triangle_bass` approximates the Triangle
channel (bass). A `layer_type="drums"` layer maps to Noise/DMC via the GM
drum map.

For strict retro authenticity, use at most 2 melodic layers + 1 bass + 1
drums layer, matching the real NES APU 5-channel limit. For denser SNES or
modern indie sound, 4–5 layers are acceptable.

nobu is game-agnostic — the same `triangle_bass` + `pulse_lead` works for
any game. Tonic and scale parameters come from the game's data, not from nobu.
