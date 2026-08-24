/* Sample 1: Simple if-else — the canonical capstone example
   Expected test cases:
   TC01: age=20 → TRUE branch → "Adult"
   TC02: age=17 → FALSE branch → "Minor"
   TC03: age=18 → boundary (>=) → "Adult"
*/
#include <stdio.h>

int classify_age(int age) {
    if (age >= 18) {
        printf("Adult\n");
        return 1;
    } else {
        printf("Minor\n");
        return 0;
    }
}

int main() {
    int age;
    scanf("%d", &age);
    classify_age(age);
    return 0;
}
