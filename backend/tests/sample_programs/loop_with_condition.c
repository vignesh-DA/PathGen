/* Sample 3: Loop with condition
   While loop summing positive numbers.
   Expected: loop-body path (i <= n, continue)
              loop-exit path (i > n, done)
*/
#include <stdio.h>

int sum_to_n(int n) {
    int sum = 0;
    int i = 1;
    while (i <= n) {
        sum = sum + i;
        i = i + 1;
    }
    printf("%d\n", sum);
    return sum;
}

int main() {
    int n;
    scanf("%d", &n);
    sum_to_n(n);
    return 0;
}
