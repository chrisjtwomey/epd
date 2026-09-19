#ifndef EPD_VERSION_COMPAT_H
#define EPD_VERSION_COMPAT_H

/**
  Whether a board and a server can work together, judged by their versions.

  They match when their major numbers match, or, while the major is 0, their
  major and minor. That is semantic versioning's own rule: before 1.0.0 a
  minor release may break the contract, and after it only a major one may.

  A version is "v1.2.3" followed by anything git describe adds, such as
  "v0.2.2-44-g2fe55a4-dirty"; the "v" is optional. Anything else, "dev" or an
  empty string, cannot be judged.
*/
typedef enum {
    VERSIONS_MATCH,
    VERSIONS_DIFFER,
    VERSIONS_UNKNOWN,   // either one is not a version this can read
} VersionMatch;

VersionMatch versionsMatch(const char* a, const char* b);

#endif  // EPD_VERSION_COMPAT_H
