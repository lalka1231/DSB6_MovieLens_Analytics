import datetime
import json
import os
import pytest
import re
import urllib.request
from collections import Counter


def _parse_csv_line(line):
    """Parse one UTF-8 CSV line, including fields enclosed in quotes."""
    values = []
    value = []
    in_quotes = False
    index = 0

    while index < len(line):
        character = line[index]
        if character == '"':
            if in_quotes and index + 1 < len(line) and line[index + 1] == '"':
                value.append('"')
                index += 1
            else:
                in_quotes = not in_quotes
        elif character == ',' and not in_quotes:
            values.append(''.join(value))
            value = []
        else:
            value.append(character)
        index += 1

    values.append(''.join(value))
    return values


def _read_rows(path, limit=1000):
    """Return at most limit data rows as dictionaries."""
    rows = []
    with open(path, 'r', encoding='utf-8') as file:
        header = _parse_csv_line(file.readline().rstrip('\n\r'))
        for line in file:
            if len(rows) == limit:
                break
            values = _parse_csv_line(line.rstrip('\n\r'))
            if len(values) == len(header):
                rows.append(dict(zip(header, values)))
    return rows


def _sorted_items(items, reverse=True):
    return dict(sorted(items, key=lambda item: ((-item[1]) if reverse else item[1], item[0])))


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _variance(values):
    average = sum(values) / len(values)
    return sum((value - average) ** 2 for value in values) / len(values)


class Ratings:
    """Analyze the first ratings from ratings.csv."""

    def __init__(self, path_to_the_file, limit=1000):
        self.rows = _read_rows(path_to_the_file, limit)

    class Movies:
        """Analyze films which occur in a Ratings object."""

        def __init__(self, ratings, path_to_movies, limit=1000):
            self.ratings = ratings if isinstance(ratings, Ratings) else Ratings(ratings, limit)
            movies = _read_rows(path_to_movies, limit)
            self.titles = {row['movieId']: row['title'] for row in movies}

        def _title(self, movie_id):
            return self.titles.get(movie_id, movie_id)

        def _ratings_by_movie(self):
            result = {}
            for row in self.ratings.rows:
                result.setdefault(row['movieId'], []).append(float(row['rating']))
            return result

        def dist_by_year(self):
            years = {}
            for row in self.ratings.rows:
                year = datetime.datetime.fromtimestamp(int(row['timestamp'])).year
                years[year] = years.get(year, 0) + 1
            return dict(sorted(years.items()))

        def dist_by_rating(self):
            ratings = {}
            for row in self.ratings.rows:
                rating = float(row['rating'])
                ratings[rating] = ratings.get(rating, 0) + 1
            return dict(sorted(ratings.items()))

        def top_by_num_of_ratings(self, n):
            counts = Counter(row['movieId'] for row in self.ratings.rows)
            items = [(self._title(movie_id), count) for movie_id, count in counts.items()]
            return dict(list(_sorted_items(items).items())[:n])

        def top_by_ratings(self, n, metric='average'):
            if metric not in ('average', 'median'):
                raise ValueError('metric must be average or median')
            values = {}
            for movie_id, ratings in self._ratings_by_movie().items():
                result = sum(ratings) / len(ratings) if metric == 'average' else _median(ratings)
                values[self._title(movie_id)] = round(result, 2)
            return dict(list(_sorted_items(values.items()).items())[:n])

        def top_controversial(self, n):
            values = {}
            for movie_id, ratings in self._ratings_by_movie().items():
                values[self._title(movie_id)] = round(_variance(ratings), 2)
            return dict(list(_sorted_items(values.items()).items())[:n])

    class Users:
        """Analyze users who created ratings."""

        def __init__(self, ratings):
            self.ratings = ratings if isinstance(ratings, Ratings) else Ratings(ratings)

        def _ratings_by_user(self):
            result = {}
            for row in self.ratings.rows:
                result.setdefault(int(row['userId']), []).append(float(row['rating']))
            return result

        def dist_by_num_of_ratings(self):
            values = [(user_id, len(ratings)) for user_id, ratings in self._ratings_by_user().items()]
            return _sorted_items(values)

        def dist_by_ratings(self, metric='average'):
            if metric not in ('average', 'median'):
                raise ValueError('metric must be average or median')
            values = []
            for user_id, ratings in self._ratings_by_user().items():
                value = sum(ratings) / len(ratings) if metric == 'average' else _median(ratings)
                values.append((user_id, round(value, 2)))
            return _sorted_items(values)

        def top_controversial(self, n):
            values = []
            for user_id, ratings in self._ratings_by_user().items():
                values.append((user_id, round(_variance(ratings), 2)))
            return dict(list(_sorted_items(values).items())[:n])


class Tags:
    """Analyze the first tags from tags.csv."""

    def __init__(self, path_to_the_file, limit=1000):
        self.rows = _read_rows(path_to_the_file, limit)

    def _unique_tags(self):
        return sorted({row['tag'] for row in self.rows})

    def most_words(self, n):
        values = [(tag, len(tag.split())) for tag in self._unique_tags()]
        return dict(list(_sorted_items(values).items())[:n])

    def longest(self, n):
        return [tag for tag in sorted(self._unique_tags(), key=lambda tag: (-len(tag), tag))[:n]]

    def most_words_and_longest(self, n):
        most_words = set(self.most_words(n))
        longest = set(self.longest(n))
        return sorted(most_words & longest)

    def most_popular(self, n):
        counts = Counter(row['tag'] for row in self.rows)
        return dict(list(_sorted_items(counts.items()).items())[:n])

    def tags_with(self, word):
        return sorted(tag for tag in self._unique_tags() if word.lower() in tag.lower())


class Movies:
    """Analyze the first movies from movies.csv."""

    def __init__(self, path_to_the_file, limit=1000):
        self.rows = _read_rows(path_to_the_file, limit)

    def dist_by_release(self):
        years = {}
        for row in self.rows:
            match = re.search(r'\((\d{4})\)$', row['title'])
            if match:
                year = int(match.group(1))
                years[year] = years.get(year, 0) + 1
        return _sorted_items(years.items())

    def dist_by_genres(self):
        genres = {}
        for row in self.rows:
            for genre in row['genres'].split('|'):
                genres[genre] = genres.get(genre, 0) + 1
        return _sorted_items(genres.items())

    def most_genres(self, n):
        values = [(row['title'], len(row['genres'].split('|'))) for row in self.rows]
        return dict(list(_sorted_items(values).items())[:n])


class Links:
    """Read links.csv and retrieve selected fields from IMDb pages when available."""

    def __init__(self, path_to_the_file, path_to_movies=None, limit=1000):
        self.rows = _read_rows(path_to_the_file, limit)
        self.titles = {}
        if path_to_movies:
            self.titles = {row['movieId']: row['title'] for row in _read_rows(path_to_movies, limit)}
        self.cache = {}

    def _title(self, movie_id):
        return self.titles.get(movie_id, movie_id)

    def _fetch_imdb(self, movie_id):
        if movie_id in self.cache:
            return self.cache[movie_id]
        row = next((item for item in self.rows if item['movieId'] == str(movie_id)), None)
        if row is None or not row.get('imdbId'):
            self.cache[movie_id] = {}
            return {}
        url = f"https://www.imdb.com/title/tt{row['imdbId'].zfill(7)}/"
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            page = urllib.request.urlopen(request, timeout=10).read().decode('utf-8')
            match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.DOTALL)
            data = json.loads(match.group(1)) if match else {}
        except (OSError, ValueError, AttributeError):
            data = {}
        self.cache[movie_id] = data
        return data

    def _field(self, data, field):
        aliases = {
            'Director': 'director',
            'Budget': 'productionBudget',
            'Cumulative Worldwide Gross': 'worldwideGross',
            'Runtime': 'duration'
        }
        value = data.get(aliases.get(field, field))
        if isinstance(value, list):
            return ', '.join(item.get('name', '') if isinstance(item, dict) else str(item) for item in value)
        if isinstance(value, dict):
            return value.get('amount')
        if field == 'Runtime' and isinstance(value, str):
            hours = re.search(r'(\d+)H', value)
            minutes = re.search(r'(\d+)M', value)
            return int(hours.group(1) if hours else 0) * 60 + int(minutes.group(1) if minutes else 0)
        return value

    def get_imdb(self, list_of_movies, list_of_fields):
        result = []
        for movie_id in list_of_movies:
            data = self._fetch_imdb(movie_id)
            result.append([int(movie_id)] + [self._field(data, field) for field in list_of_fields])
        return sorted(result, key=lambda row: row[0], reverse=True)

    def _info_for_first_movies(self, number):
        movie_ids = [row['movieId'] for row in self.rows[:max(number, 1)]]
        return [(movie_id, self._fetch_imdb(movie_id)) for movie_id in movie_ids]

    def top_directors(self, n):
        directors = Counter()
        for _, data in self._info_for_first_movies(n * 10):
            value = self._field(data, 'Director')
            if value:
                for director in value.split(', '):
                    directors[director] += 1
        return dict(list(_sorted_items(directors.items()).items())[:n])

    def most_expensive(self, n):
        values = []
        for movie_id, data in self._info_for_first_movies(n * 10):
            budget = self._field(data, 'Budget')
            if isinstance(budget, (int, float)):
                values.append((self._title(movie_id), budget))
        return dict(list(_sorted_items(values).items())[:n])

    def most_profitable(self, n):
        values = []
        for movie_id, data in self._info_for_first_movies(n * 10):
            budget = self._field(data, 'Budget')
            gross = self._field(data, 'Cumulative Worldwide Gross')
            if isinstance(budget, (int, float)) and isinstance(gross, (int, float)):
                values.append((self._title(movie_id), gross - budget))
        return dict(list(_sorted_items(values).items())[:n])

    def longest(self, n):
        values = []
        for movie_id, data in self._info_for_first_movies(n * 10):
            runtime = self._field(data, 'Runtime')
            if isinstance(runtime, int):
                values.append((self._title(movie_id), runtime))
        return dict(list(_sorted_items(values).items())[:n])

    def top_cost_per_minute(self, n):
        values = []
        for movie_id, data in self._info_for_first_movies(n * 10):
            budget = self._field(data, 'Budget')
            runtime = self._field(data, 'Runtime')
            if isinstance(budget, (int, float)) and isinstance(runtime, int) and runtime:
                values.append((self._title(movie_id), round(budget / runtime, 2)))
        return dict(list(_sorted_items(values).items())[:n])


class Tests:
    """PyTest checks. Set MOVIELENS_PATH to the folder with four CSV files."""

    def _path(self):
        path = os.environ.get('MOVIELENS_PATH')
        if not path:
            pytest.skip('MOVIELENS_PATH is not set')
        return path

    def _descending(self, values):
        return list(values) == sorted(values, reverse=True)

    def _links_with_fake_imdb(self, monkeypatch):
        path = self._path()
        links = Links(f'{path}/links.csv', f'{path}/movies.csv')

        def fake_imdb(movie_id):
            movie_number = int(movie_id)
            return {
                'director': [{'name': f'Director {movie_number % 3}'}],
                'productionBudget': {'amount': movie_number * 100},
                'worldwideGross': {'amount': movie_number * 200},
                'duration': 'PT2H10M'
            }

        monkeypatch.setattr(links, '_fetch_imdb', fake_imdb)
        return links

    def test_ratings_movies_methods(self):
        path = self._path()
        ratings = Ratings(f'{path}/ratings.csv')
        movies = Ratings.Movies(ratings, f'{path}/movies.csv')
        by_year = movies.dist_by_year()
        by_rating = movies.dist_by_rating()
        by_count = movies.top_by_num_of_ratings(3)
        by_average = movies.top_by_ratings(3)
        controversial = movies.top_controversial(3)
        assert isinstance(by_year, dict) and list(by_year) == sorted(by_year)
        assert isinstance(by_rating, dict) and list(by_rating) == sorted(by_rating)
        assert isinstance(by_count, dict) and self._descending(by_count.values())
        assert isinstance(by_average, dict) and self._descending(by_average.values())
        assert isinstance(controversial, dict) and self._descending(controversial.values())

    def test_ratings_users_methods(self):
        users = Ratings.Users(Ratings(f'{self._path()}/ratings.csv'))
        by_count = users.dist_by_num_of_ratings()
        by_ratings = users.dist_by_ratings()
        controversial = users.top_controversial(3)
        assert isinstance(by_count, dict) and self._descending(by_count.values())
        assert isinstance(by_ratings, dict) and self._descending(by_ratings.values())
        assert isinstance(controversial, dict) and self._descending(controversial.values())

    def test_tags_methods(self):
        tags = Tags(f'{self._path()}/tags.csv')
        words = tags.most_words(3)
        longest = tags.longest(3)
        both = tags.most_words_and_longest(3)
        popular = tags.most_popular(3)
        matching = tags.tags_with('fun')
        assert isinstance(words, dict) and self._descending(words.values())
        assert isinstance(longest, list) and all(isinstance(tag, str) for tag in longest)
        assert isinstance(both, list) and all(isinstance(tag, str) for tag in both)
        assert isinstance(popular, dict) and self._descending(popular.values())
        assert isinstance(matching, list) and matching == sorted(matching)

    def test_movies_methods(self):
        movies = Movies(f'{self._path()}/movies.csv')
        release = movies.dist_by_release()
        genres = movies.dist_by_genres()
        most_genres = movies.most_genres(3)
        assert isinstance(release, dict) and self._descending(release.values())
        assert isinstance(genres, dict) and self._descending(genres.values())
        assert isinstance(most_genres, dict) and self._descending(most_genres.values())

    def test_links_methods(self, monkeypatch):
        links = self._links_with_fake_imdb(monkeypatch)
        imdb = links.get_imdb([1, 2], ['Director', 'Budget', 'Runtime'])
        directors = links.top_directors(2)
        expensive = links.most_expensive(2)
        profitable = links.most_profitable(2)
        longest = links.longest(2)
        costs = links.top_cost_per_minute(2)
        assert isinstance(imdb, list) and imdb[0][0] > imdb[1][0]
        assert isinstance(directors, dict) and self._descending(directors.values())
        assert isinstance(expensive, dict) and self._descending(expensive.values())
        assert isinstance(profitable, dict) and self._descending(profitable.values())
        assert isinstance(longest, dict) and self._descending(longest.values())
        assert isinstance(costs, dict) and self._descending(costs.values())


def main():
    print('Import movielens_analysis.py in a Jupyter Notebook or run its PyTest checks.')


if __name__ == '__main__':
    main()
