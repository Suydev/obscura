/* musl/aarch64 does not provide __clear_cache(), which V8's ARM64 JIT
 * references (v8/src/codegen/arm64/cpu-arm64.cc). glibc does. Supply it so
 * the aarch64-unknown-linux-musl link can complete.
 *
 * Standard AArch64 cache-maintenance sequence: clean D-cache to the point of
 * unification, sync, invalidate I-cache, sync, flush the pipeline. Operates on
 * 64-byte granules, which is the AArch64 minimum cache line.
 */
#include <stdint.h>

void __clear_cache(char *start, char *end)
{
	uintptr_t first = (uintptr_t)start & ~(uintptr_t)63;
	uintptr_t last = (uintptr_t)end;

	for (uintptr_t a = first; a < last; a += 64)
		__asm__ volatile("dc cvau, %0" :: "r"(a) : "memory");
	__asm__ volatile("dsb ish" ::: "memory");

	for (uintptr_t a = first; a < last; a += 64)
		__asm__ volatile("ic ivau, %0" :: "r"(a) : "memory");
	__asm__ volatile("dsb ish\n\tisb" ::: "memory");
}
