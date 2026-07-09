// 04-combination/combine-latest.ts
// Merges values from multiple Observables into a single Observable
//
// pnpm exec ts-node 04-combination\combine-latest.ts

import { combineLatest, interval, take } from 'rxjs';

combineLatest([
  interval(500).pipe(take(10)),
  interval(3000).pipe(take(10))
]).subscribe(console.log);


/* Note: combineLatest works with active streams. With completed streams, consider using forkJoin or zip instead. */