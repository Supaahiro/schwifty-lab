// 01-creation/interval.ts
// Outputs an incremental number at intervals
// 
// pnpm exec ts-node 01-creation\interval.ts

import { interval, take } from 'rxjs';

interval(1000).pipe(take(3)).subscribe(console.log)