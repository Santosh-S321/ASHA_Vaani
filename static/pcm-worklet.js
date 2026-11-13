// Converts mic audio to what Prisma v3.0 expects: 16 kHz, 16-bit little-endian mono PCM,
// 512 samples (1,024 bytes) per frame, posted in real time.
class Pcm16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;   // e.g. 48000 -> 3
    this.pos = 0; this.acc = 0; this.cnt = 0;
    this.buf = new Int16Array(512); this.n = 0;
  }
  push(s) {
    s = Math.max(-1, Math.min(1, s));
    this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    if (this.n === 512) {
      this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
      this.buf = new Int16Array(512); this.n = 0;
    }
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc += ch[i]; this.cnt++; this.pos += 1;
      if (this.pos >= this.ratio) {      // box average = simple low-pass before decimating
        this.pos -= this.ratio;
        this.push(this.acc / this.cnt);
        this.acc = 0; this.cnt = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm16k", Pcm16k);
