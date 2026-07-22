# Sistemas de Música Adaptativa (Interactive Music)

Fontes: A Composer's Guide to Game Music (Winifred Phillips), documentação técnica de Wwise/FMOD, análises de implementação em Unity/Godot.

## 1. Por que música de jogo é diferente de música linear
Trilha de filme é composta para um timeline FIXO. Trilha de jogo precisa responder a um timeline VARIÁVEL — o jogador controla duração de exploração, momento de combate, resultado de boss. A música precisa ser um SISTEMA reativo, não uma peça fixa.

## 2. As duas técnicas fundamentais

### Vertical Layering (reorquestração vertical)
- A composição é dividida em CAMADAS instrumentais (bateria, baixo, cordas, melodia, percussão de tensão) que tocam SIMULTANEAMENTE e em sincronia (mesmo tempo, mesma harmonia).
- O sistema ativa/desativa camadas conforme o estado do jogo, sem parar a música — ex.: exploração = só cordas suaves; ao entrar em combate, entram bateria e baixo por cima, sem interromper o loop.
- **Vantagem**: transições instantâneas e suaves, ótimo para estados que mudam rapidamente (ex.: HP do boss, proximidade de inimigo).
- **Desvantagem**: exige que todas as camadas sejam compostas para funcionar harmonicamente juntas o tempo todo — mais trabalho de composição upfront.
- Exemplo clássico: Hollow Knight (camadas de intensidade por área), Diablo (camadas ambiente vs. combate).

### Horizontal Resequencing (resequenciamento horizontal)
- A composição é dividida em SEGMENTOS/blocos musicais discretos (intro, loop A, loop B, transição, clímax) que são encadeados dinamicamente pelo sistema, geralmente respeitando pontos de sincronismo musical (fim de frase, fim de compasso).
- O sistema escolhe qual segmento tocar A SEGUIR baseado no estado do jogo, mas espera o ponto de sincronismo correto antes de trocar (evita cortes abruptos no meio de uma frase).
- **Vantagem**: permite mudanças estruturais reais (mudança de tonalidade, andamento, instrumentação completa) — ideal para jogos com fases distintas de exploração > tensão > boss.
- **Desvantagem**: transição não é instantânea (espera o próximo ponto de sync), pode ter delay perceptível se os segmentos forem longos.
- Exemplo clássico: Legend of Zelda (mudança de área = nova música completa), Undertale (segmentos de batalha ligados a eventos de diálogo).

### Sistema híbrido (o mais usado em produção moderna)
- Combina as duas técnicas: horizontal resequencing para trocas de REGIÃO/FASE, vertical layering DENTRO de cada região para reagir a intensidade momentânea (ex.: combate dentro da mesma área).

## 3. Stingers (pontuações musicais curtas)
- **Stinger**: fragmento musical curto (1-4 segundos) tocado sobre a música de fundo para pontuar um evento específico (item coletado, dano recebido, quebra-cabeça resolvido, novo inimigo detectado).
- Deve ser harmonicamente compatível com a música de fundo em qualquer ponto (geralmente atonal/percussivo, ou escrito na tonalidade principal do jogo).
- Stingers de "descoberta" (item raro, segredo) tendem a usar intervalos ascendentes e brilhantes; stingers de "perigo" usam dissonância ou percussão seca.

## 4. Grafo de estados de música (music state machine)
Ao desenhar um sistema adaptativo, primeiro modele como uma máquina de estados:
[Exploração] --(inimigo detectado)--> [Alerta] --(combate iniciado)--> [Combate]
[Combate] --(inimigo derrotado)--> [Exploração]
[Combate] --(HP jogador < 20%)--> [Combate Tenso] (camada extra de percussão)
[Qualquer estado] --(boss encontrado)--> [Boss Intro] --(fim de intro)--> [Boss Loop]
[Boss Loop] --(boss HP < 30%)--> [Boss Fase 2] (horizontal resequencing)
[Qualquer estado] --(vitória)--> [Stinger Vitória] --> [Exploração]

Cada transição deve ser documentada com: TIPO (vertical/horizontal/stinger), PONTO DE SYNC exigido (imediato, fim de compasso, fim de frase), e CONDIÇÃO de gatilho (evento de gameplay).

## 5. Loop points e loop sem costura (seamless loop)
- Todo loop de exploração precisa de LOOP POINT preciso: o fim do arquivo deve encaixar harmonicamente e ritmicamente com o início, sem silêncio perceptível ou "salto" de tempo.
- Técnica prática: compor em número de compassos múltiplo de 4 ou 8 (facilita edição e sincronização com engine), e testar o loop repetido 5-10 vezes seguidas para detectar cliques ou quebras de fase.
- Em engines simples (Godot/Unity), usar metadata de loop start/end embutida no arquivo (formatos OGG com loop tags, ou WAV com cue points) em vez de depender só do loop automático do player.

## 6. Parameter-driven mixing (mixagem por parâmetro contínuo)
- Em vez de estados discretos, alguns sistemas usam um parâmetro CONTÍNUO (ex.: "intensidade de combate" de 0 a 1) que cruza-fadeia (crossfade) entre camadas ou stems proporcionalmente.
- Usado em Wwise via RTPC (Real-Time Parameter Control) e em FMOD via Parameters — o volume de cada stem é uma curva em função do parâmetro, não um on/off binário.
- Vantagem: transições ainda mais orgânicas, sem "saltos" perceptíveis entre estados.

## 7. Diegetic vs. non-diegetic
- **Diegética**: música que existe no mundo do jogo (rádio, jukebox, banda tocando na cena) — pode ser abafada por distância/paredes, sujeita a física do som.
- **Não-diegética**: trilha tradicional, o jogador não "ouve" a fonte, é puramente para a experiência do espectador/jogador.
- Jogos modernos às vezes misturam as duas (ex.: entrar em uma taverna faz a trilha de fundo "abaixar" e uma música diegética de banda tocando ao vivo assumir).

## 8. Ducking
- Redução temporária de volume de uma camada (geralmente música) quando outro elemento de áudio prioritário precisa de destaque (diálogo, efeito sonoro crítico, aviso de perigo).
- Implementado tipicamente como um efeito de compressor lateral (sidechain) acionado pelo canal de voz/SFX.
