// 01-creation/of.ts
// Synchronous emission of values
// 
// pnpm exec ts-node 01-creation\of.ts

import { of } from 'rxjs';

of(1, 2, 3).subscribe(console.log)