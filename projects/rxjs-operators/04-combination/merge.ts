// 04-combination/merge.ts
// Merges values from multiple Observables into a single Observable
//
// pnpm exec ts-node 04-combination\merge.ts

import { merge, of } from "rxjs";

merge(of('A'), of('B')).subscribe(console.log)