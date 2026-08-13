export type PasswordStrength = "poor" | "good" | "strong" | "high";

const COMMON_PASSWORDS = new Set([
  "123456",
  "password",
  "12345678",
  "qwerty",
  "123456789",
  "12345",
  "1234",
  "111111",
  "1234567",
  "dragon",
  "123123",
  "baseball",
  "abc123",
  "football",
  "monkey",
  "letmein",
  "shadow",
  "master",
  "666666",
  "qwertyuiop",
  "123321",
  "mustang",
  "1234567890",
  "michael",
  "654321",
  "superman",
  "1qaz2wsx",
  "7777777",
  "121212",
  "000000",
  "qazwsx",
  "123qwe",
  "killer",
  "trustno1",
  "jordan",
  "jennifer",
  "zxcvbnm",
  "asdfgh",
  "hunter",
  "buster",
  "soccer",
  "harley",
  "batman",
  "andrew",
  "tigger",
  "sunshine",
  "iloveyou",
  "2000",
  "charlie",
  "robert",
  "thomas",
  "hockey",
  "ranger",
  "daniel",
  "starwars",
  "klaster",
  "112233",
  "george",
  "computer",
  "michelle",
  "jessica",
  "pepper",
  "1111",
  "zxcvbn",
  "555555",
  "11111111",
  "131313",
  "freedom",
  "777777",
  "pass",
  "maggie",
  "159753",
  "aaaaaa",
  "ginger",
  "princess",
  "joshua",
  "cheese",
  "amanda",
  "summer",
  "love",
  "ashley",
  "nicole",
  "chelsea",
  "biteme",
  "matthew",
  "access",
  "yankees",
  "987654321",
  "dallas",
  "austin",
  "thunder",
  "taylor",
  "matrix",
  "mobilemail",
  "admin",
  "admin123",
  "welcome",
  "password1",
  "passw0rd",
  "qwerty123",
  "test",
  "test123",
  "hello",
  "hello123",
  "secret",
]);

const SEQUENCES =
  /(?:abcdefgh|bcdefghi|cdefghij|defghijk|efghijkl|fghijklm|ghijklmn|hijklmno|ijklmnop|jklmnopq|klmnopqr|lmnopqrs|mnopqrst|nopqrstu|opqrstuv|pqrstuvw|qrstuvwx|rstuvwxy|stuvwxyz|abcdefg|bcdefgh|cdefghi|defghij|efghijk|fghijkl|ghijklm|hijklmn|ijklmno|jklmnop|klmnopq|lmnopqr|mnopqrs|nopqrst|opqrstu|pqrstuv|qrstuvw|rstuvwx|stuvwxy|tuvwxyz|abcdef|bcdefg|cdefgh|defghi|efghij|fghijk|ghijkl|hijklm|ijklmn|jklmno|klmnop|lmnopq|mnopqr|nopqrs|opqrst|pqrstu|qrstuv|rstuvw|stuvwx|tuvwxy|uvwxyz|0123456789|01234567|12345678|23456789|0123456|1234567|2345678|3456789|012345|123456|234567|345678|456789|01234|12345|23456|34567|45678|56789)/i;

export function passwordStrength(pw: string): PasswordStrength {
  const len = pw.length;
  if (len === 0) return "poor";
  if (len < 6 || COMMON_PASSWORDS.has(pw.toLowerCase())) return "poor";

  const lower = /[a-z]/.test(pw);
  const upper = /[A-Z]/.test(pw);
  const digit = /[0-9]/.test(pw);
  const symbol = /[^A-Za-z0-9]/.test(pw);
  const classes = Number(lower) + Number(upper) + Number(digit) + Number(symbol);
  const uniq = new Set(pw).size;
  const repeats = /(.)\1{2,}/.test(pw);

  let score = 0;
  score += len * 4;
  score += classes * 10;
  score += Math.min(uniq * 2, 20);
  if (pw.length >= 12) score += 8;
  if (classes >= 3 && len >= 10) score += 8;
  if (repeats) score -= 15;
  if (SEQUENCES.test(pw)) score -= 10;

  if (score < 42) return "poor";
  if (score < 68) return "good";
  if (score < 96) return "strong";
  return "high";
}
