// 01-creation/timer.ts
// Emits after a delay (and optionally at intervals)
//
// pnpm exec ts-node 01-creation\timer.ts

import { take, timer } from 'rxjs';

timer(2000, 1000).pipe(take(3)).subscribe(console.log)