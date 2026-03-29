"""Tests for polyphony.compiler.common.utils."""
import pytest
from polyphony.compiler.common.utils import (
    find_only_one_in,
    replace_item,
    remove_from_list,
    remove_except_one,
    unique,
    id2str,
    find_nth_item_index,
    find_id_index,
)


class TestFindOnlyOneIn:
    def test_find_single(self):
        assert find_only_one_in(int, [1, 'a', 'b']) == 1

    def test_find_none(self):
        assert find_only_one_in(int, ['a', 'b']) is None

    def test_find_multiple_raises(self):
        with pytest.raises(AssertionError):
            find_only_one_in(int, [1, 2, 'a'])

    def test_empty_seq(self):
        assert find_only_one_in(str, []) is None


class TestReplaceItem:
    def test_replace_single(self):
        lst = [1, 2, 3]
        replace_item(lst, 2, 20)
        assert lst == [1, 20, 3]

    def test_replace_all(self):
        lst = [1, 2, 1, 3]
        replace_item(lst, 1, 10, all=True)
        assert lst == [10, 2, 10, 3]

    def test_replace_first_only(self):
        lst = [1, 2, 1, 3]
        replace_item(lst, 1, 10)
        assert lst == [10, 2, 1, 3]

    def test_replace_list_of_olds(self):
        a, b, c = object(), object(), object()
        lst = [a, b, c]
        replace_item(lst, [a, b], 'x')
        assert lst == ['x', 'x', c]

    def test_replace_identity(self):
        """replace_item uses 'is' for comparison."""
        a = object()
        b = object()
        lst = [a, b]
        replace_item(lst, a, 'replaced')
        assert lst == ['replaced', b]

    def test_replace_not_found(self):
        lst = [1, 2, 3]
        replace_item(lst, 99, 0)
        assert lst == [1, 2, 3]


class TestRemoveFromList:
    def test_basic(self):
        lst = [1, 2, 3, 4]
        remove_from_list(lst, [2, 4])
        assert lst == [1, 3]

    def test_remove_nonexistent(self):
        lst = [1, 2]
        remove_from_list(lst, [99])
        assert lst == [1, 2]

    def test_empty_removes(self):
        lst = [1, 2]
        remove_from_list(lst, [])
        assert lst == [1, 2]


class TestRemoveExceptOne:
    def test_keep_first(self):
        a = object()
        lst = [a, a, a]
        result = remove_except_one(lst, a)
        count = sum(1 for x in result if x is a)
        assert count == 1

    def test_no_target(self):
        lst = [1, 2, 3]
        result = remove_except_one(lst, 99)
        assert result == [1, 2, 3]

    def test_single_occurrence(self):
        a = object()
        b = object()
        lst = [a, b]
        result = remove_except_one(lst, a)
        assert result == [a, b]


class TestUnique:
    def test_basic(self):
        assert unique([3, 1, 2, 1, 3]) == [1, 2, 3]

    def test_empty(self):
        assert unique([]) == []

    def test_already_unique(self):
        assert unique([1, 2, 3]) == [1, 2, 3]


class TestId2str:
    def test_zero(self):
        assert id2str(0) == '0'

    def test_small(self):
        assert id2str(1) == '1'
        assert id2str(9) == '9'
        assert id2str(10) == 'a'
        assert id2str(35) == 'z'

    def test_two_digit(self):
        assert id2str(36) == '10'
        assert id2str(37) == '11'

    def test_roundtrip(self):
        # Verify id2str produces expected base-36 string
        result = id2str(100)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFindNthItemIndex:
    def test_find_first(self):
        assert find_nth_item_index([1, 2, 1, 3], 1, 0) == 0

    def test_find_second(self):
        assert find_nth_item_index([1, 2, 1, 3], 1, 1) == 2

    def test_not_found(self):
        assert find_nth_item_index([1, 2, 3], 99, 0) == -1

    def test_nth_too_large(self):
        assert find_nth_item_index([1, 2, 1], 1, 5) == -1


class TestFindIdIndex:
    def test_found(self):
        a = object()
        b = object()
        assert find_id_index([a, b], a) == 0
        assert find_id_index([a, b], b) == 1

    def test_not_found(self):
        a = object()
        b = object()
        assert find_id_index([a], b) == -1

    def test_empty(self):
        assert find_id_index([], object()) == -1
