numbers = [1, 20, 3, 40]
for num in numbers:
    if num > 10:
        numbers.remove(num)  # This messes up the loop!
print(numbers)  # Output: [1, 3, 40] (missed 40!)
