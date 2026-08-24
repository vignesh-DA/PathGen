/* Sample 2: Nested if-else
   Expected conditions: score >= 90, score >= 75, score >= 50
   Expected paths: 4 (A, B, C, F grade)
*/
#include <stdio.h>

int grade(int score) {
    if (score >= 90) {
        printf("A\n");
        return 4;
    } else if (score >= 75) {
        printf("B\n");
        return 3;
    } else if (score >= 50) {
        printf("C\n");
        return 2;
    } else {
        printf("F\n");
        return 1;
    }
}

int main() {
    int score;
    scanf("%d", &score);
    grade(score);
    return 0;
}
