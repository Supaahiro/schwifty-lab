// 04-combination/fork-join.ts
// Combines multiple Observables and emits the last values when all complete
//
// pnpm exec ts-node 04-combination/fork-join.ts

import { forkJoin, of } from 'rxjs';

forkJoin([of(1, 2), of(3, 4)]).subscribe(console.log);