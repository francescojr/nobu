# Pipeline de Produção e Integração com Engines

Baseado em práticas de produção de game audio e documentação de integração Wwise/FMOD/Godot/Unity.

## 0. nobu folder conventions

| Artifact | Path |
|---|---|
| MIDI (MCP / examples) | `assets/midi/` |
| SoundFonts (`.sf2`) | `assets/soundfonts/` |
| Rendered `.ogg` / `.wav` | `output/audio/{project}/wav/` and `.../ogg/` |

```bash
# Compose (demo or via nobu MCP export_midi)
python examples/demo_biome_ost.py

# Render all MIDI → OGG/WAV (or use MCP render_project / render_all_modes)
python scripts/render_midi.py --mode chip
python scripts/render_midi.py --soundfont assets/soundfonts/default.sf2
```

Copy finished audio from `output/audio/{project}/` into your game's runtime path
(e.g. `res://audio/music/` in Godot, `Assets/Audio/Music/` in Unity).

## 1. Pipeline padrão de produção de trilha para jogo
1. **Briefing de design**: receber GDD/level design doc, entender pilares emocionais de cada estado de jogo.
2. **Sketch de leitmotifs**: compor temas centrais em MIDI (protótipo rápido, ver midi-code-cookbook.md) antes de qualquer produção de áudio final.
3. **Prototipagem em engine**: implementar versão simplificada do sistema adaptativo (mesmo com MIDI placeholder) para validar transições e loop no contexto real de gameplay.
4. **Produção final**: gravação/síntese de áudio de alta qualidade, mixagem e masterização por camada/stem.
5. **Implementação técnica**: integração via middleware (Wwise/FMOD) ou sistema nativo da engine (Godot AudioStreamPlayer, Unity AudioSource + Timeline).
6. **QA de áudio**: testar todos os estados e transições em playtest real, verificar loops, volumes relativos e ausência de cliques/pops.

## 2. Formatos de entrega comuns
- **Stems separados por camada** (WAV 24-bit/48kHz é o padrão de produção): cada instrumento/grupo em arquivo próprio para controle de vertical layering na engine.
- **MIDI de referência**: útil para a equipe de audio programming ajustar timing/sync sem depender do compositor para cada iteração pequena.
- **Loop metadata**: para formatos como OGG Vorbis, usar tags de loop (LOOPSTART/LOOPLENGTH) reconhecidas por engines como Godot; para WAV, usar cue points/smpl chunk.
- **Middleware project files**: se usando Wwise/FMOD, entregar o projeto do middleware (.wproj/.fspro) integrado ao repositório do jogo, não apenas os áudios brutos.

## 3. Integração simplificada em Godot
```gdscript
extends Node

@onready var layer_explore = $LayerExplore
@onready var layer_combat = $LayerCombat

func set_combat_intensity(active: bool):
    var target_volume = 0.0 if active else -80.0
    layer_combat.volume_db = target_volume
    layer_explore.volume_db = -80.0 if active else 0.0
```
Nota prática: os players devem estar sincronizados no MESMO ponto de playback (iniciados juntos, ou usando `AudioStreamPlayer.get_playback_position()` para realinhar) para vertical layering funcionar sem drift.

## 4. Integração simplificada em Unity
```csharp
public class MusicLayerController : MonoBehaviour {
    public AudioSource exploreLayer;
    public AudioSource combatLayer;
    public float fadeSpeed = 1.5f;

    public void SetCombat(bool active) {
        StartCoroutine(FadeLayer(combatLayer, active ? 1f : 0f));
        StartCoroutine(FadeLayer(exploreLayer, active ? 0f : 1f));
    }

    System.Collections.IEnumerator FadeLayer(AudioSource src, float target) {
        while (!Mathf.Approximately(src.volume, target)) {
            src.volume = Mathf.MoveTowards(src.volume, target, fadeSpeed * Time.deltaTime);
            yield return null;
        }
    }
}
```

## 5. Quando usar middleware dedicado (Wwise/FMOD) vs. sistema nativo
- **Sistema nativo (Godot/Unity puro)**: suficiente para jogos indie pequenos, 2-4 estados de música, poucas camadas. Menor overhead de integração e licenciamento.
- **Middleware (Wwise/FMOD)**: necessário quando o jogo exige RTPC contínuo (parameter-driven mixing), muitos estados/transições complexas, ou equipe de áudio dedicada trabalhando em paralelo à programação.
- Wwise tende a ser usado em produções AAA/maiores (é gratuito até certo limite de revenue); FMOD é mais comum em produções indie/médias por ter licenciamento mais simples para times pequenos.

## 6. Checklist de entrega final
- Todos os estados do grafo de música têm áudio final renderizado e testado em loop?
- As transições foram testadas no CONTEXTO real de gameplay, não apenas ouvindo linear?
- Os stems estão nomeados e organizados de forma que a equipe de programação de áudio entenda sem precisar perguntar ao compositor?
- Existe documentação (mesmo que simples) do grafo de estados e das condições de transição?
- O volume relativo entre camadas foi calibrado para o mix final do jogo (não apenas isolado no DAW)?
