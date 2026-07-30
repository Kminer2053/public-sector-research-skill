// Capture, normalize, crossfade, and QA all seven scenes.
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const CLIPS = path.join(ROOT, 'clips');
const QA = path.join(ROOT, 'qa');
const FINAL = path.join(ROOT, 'final');
const DURATIONS = [6.0, 4.5, 24.0, 8.5, 7.0, 6.0, 6.0];
const NAMES = ['intro', 'hero', 'overview', 'findings', 'recommendations', 'review', 'outro'];
const XFADE = 0.333;
const REUSE_CLIPS = process.env.REUSE_CLIPS === '1' || process.argv.includes('--reuse');
const scenesArgument = process.argv.find((value) => value.startsWith('--scenes='));
const SELECTED_SCENES = scenesArgument
  ? new Set(scenesArgument.slice('--scenes='.length).split(',').map(Number))
  : null;

for (const dir of [CLIPS, QA, FINAL]) fs.mkdirSync(dir, { recursive: true });

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: ROOT, encoding: 'utf8', ...options });
  if (result.status !== 0) {
    process.stderr.write(result.stdout || '');
    process.stderr.write(result.stderr || '');
    process.exit(result.status || 1);
  }
  return result;
}

const clips = [];
for (let id = 0; id < DURATIONS.length; id += 1) {
  const clip = path.join(CLIPS, `${String(id).padStart(2, '0')}_${NAMES[id]}.mp4`);
  const shouldCapture = SELECTED_SCENES
    ? SELECTED_SCENES.has(id)
    : !REUSE_CLIPS || !fs.existsSync(clip);
  if (shouldCapture) {
    const capture = run(process.execPath, ['gen.js', String(id)]);
    process.stdout.write(capture.stdout);
    const line = capture.stdout.trim().split('\n').at(-1);
    const meta = JSON.parse(line);
    const start = (meta.preRollMs / 1000).toFixed(3);
    run('ffmpeg', [
      '-y', '-ss', start, '-i', meta.webm,
      '-vf', 'fps=30,tpad=stop_mode=clone:stop_duration=5',
      '-t', String(DURATIONS[id]), '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', clip,
    ]);
  }
  const contact = path.join(QA, `${String(id).padStart(2, '0')}_${NAMES[id]}_contact.png`);
  run('ffmpeg', [
    '-y', '-i', clip, '-vf', `fps=9/${DURATIONS[id]},scale=640:360,tile=3x3`,
    '-frames:v', '1', '-update', '1', contact,
  ]);
  clips.push(clip);
}

const ffmpegArgs = ['-y'];
clips.forEach((clip) => ffmpegArgs.push('-i', clip));
const filters = clips.map((_, index) => `[${index}:v]fps=30,format=yuv420p,settb=AVTB[v${index}]`);
let current = 'v0';
let cumulative = DURATIONS[0];
for (let index = 1; index < clips.length; index += 1) {
  const offset = cumulative - XFADE * index;
  const output = `x${index}`;
  filters.push(`[${current}][v${index}]xfade=transition=fade:duration=${XFADE}:offset=${offset.toFixed(3)}[${output}]`);
  current = output;
  cumulative += DURATIONS[index];
}

const finalVideo = path.join(FINAL, 'bokri_walkthrough_60s.mp4');
ffmpegArgs.push(
  '-filter_complex', filters.join(';'), '-map', `[${current}]`,
  '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-pix_fmt', 'yuv420p',
  '-r', '30', '-movflags', '+faststart', '-an', finalVideo,
);
run('ffmpeg', ffmpegArgs);

const finalContact = path.join(FINAL, 'bokri_walkthrough_60s_contact.png');
run('ffmpeg', [
  '-y', '-i', finalVideo, '-vf', 'fps=12/60,scale=480:270,tile=4x3',
  '-frames:v', '1', '-update', '1', finalContact,
]);

console.log(JSON.stringify({ finalVideo, finalContact, clips }, null, 2));
