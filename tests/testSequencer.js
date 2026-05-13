const Sequencer = require("@jest/test-sequencer").default;

const ORDER = [
  "manual.test.ts",
  "unit.test.ts",
  "security.test.ts",
  "functional.test.ts",
];

class TestSequencer extends Sequencer {
  sort(tests) {
    return [...tests].sort((a, b) => {
      const ai = ORDER.findIndex((name) => a.path.endsWith(name));
      const bi = ORDER.findIndex((name) => b.path.endsWith(name));
      const aRank = ai === -1 ? ORDER.length : ai;
      const bRank = bi === -1 ? ORDER.length : bi;
      return aRank - bRank;
    });
  }
}

module.exports = TestSequencer;
