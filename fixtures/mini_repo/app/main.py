"""Application entrypoint."""

from app.core import boot
from app.db import save


def main() -> str:
    result = boot()
    save({"status": result})
    return result


if __name__ == "__main__":
    print(main())
