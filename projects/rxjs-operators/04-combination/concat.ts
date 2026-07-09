// 04-combination/concat.ts
// Emits values in sequence from multiple Observables
//
// pnpm exec ts-node 04-combination\concat.ts

import { concat, of } from "rxjs";

concat(of(1, 2), of(3, 4)).subscribe(console.log)