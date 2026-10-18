use std::{path::Path, time::Instant};
use voxtype::{
    config::WhisperConfig,
    transcribe::{parakeet_cpp::ParakeetCppTranscriber, whisper::WhisperTranscriber, Transcriber},
};
fn main() -> anyhow::Result<()> {
    let model = std::env::args()
        .nth(1)
        .expect("model: redux | tiny.en | base.en");
    let vad = std::path::PathBuf::from(
        std::env::var("VOXTYPE_VAD_FIXTURES").unwrap_or_else(|_| "tests/fixtures/vad".into()),
    );
    let cpp = std::path::PathBuf::from(
        std::env::var("VOXTYPE_PARAKEET_SOURCE")
            .expect("set VOXTYPE_PARAKEET_SOURCE to the parakeet.cpp checkout"),
    );
    let model_path = std::env::var("VOXTYPE_REDUX_MODEL").expect("set VOXTYPE_REDUX_MODEL");
    let paths = [
        vad.join("speech_hello.wav"),
        vad.join("speech_long.wav"),
        cpp.join("tests/fixtures/speech.wav"),
        cpp.join("tests/fixtures/two_speakers.wav"),
    ];
    let start = Instant::now();
    let redux;
    let whisper;
    let infer: Box<dyn Fn(&[f32]) -> Result<String, voxtype::error::TranscribeError>> =
        if model == "redux" {
            redux = ParakeetCppTranscriber::new(Path::new(&model_path))?;
            Box::new(move |s| redux.transcribe(s))
        } else {
            let mut config = WhisperConfig::default();
            config.model = model.clone();
            whisper = WhisperTranscriber::new(&config)?;
            Box::new(move |s| whisper.transcribe(s))
        };
    println!(
        "{}",
        serde_json::json!({"model":model,"load_seconds":start.elapsed().as_secs_f64()})
    );
    for path in paths {
        let mut wav = hound::WavReader::open(&path)?;
        assert_eq!(wav.spec().sample_rate, 16000);
        assert_eq!(wav.spec().channels, 1);
        let samples: Vec<f32> = wav
            .samples::<i16>()
            .map(|s| s.unwrap() as f32 / 32768.0)
            .collect();
        let warmup = infer(&samples)?;
        let mut times = Vec::new();
        let mut transcripts = Vec::new();
        for _ in 0..3 {
            let start = Instant::now();
            let text = infer(&samples)?;
            times.push(start.elapsed().as_secs_f64());
            transcripts.push(text);
        }
        let mut sorted = times.clone();
        sorted.sort_by(f64::total_cmp);
        println!(
            "{}",
            serde_json::json!({"model":model,"file":path,"audio_seconds":samples.len() as f64/16000.0,"seconds":times,"median_seconds":sorted[1],"warmup_transcript":warmup,"transcripts":transcripts})
        );
    }
    Ok(())
}
