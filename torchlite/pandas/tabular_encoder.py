"""
A structured data encoder based on sklearn API
"""
import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from pandas.api.types import is_numeric_dtype


class BaseEncoder(BaseEstimator, TransformerMixin):
    def __init__(self, numeric_vars, categorical_vars, fix_missing, numeric_scaler):
        self.categorical_vars = categorical_vars
        self.numeric_vars = numeric_vars
        self.tfs_list = {}
        self.numeric_scaler = numeric_scaler
        self.fix_missing = fix_missing

    def _get_all_non_numeric(self, df):
        non_num_cols = []
        for col in df.columns:
            if not is_numeric_dtype(df[col]):
                non_num_cols.append(col)
        return non_num_cols

    def _check_integrity(self, df):
        """
        Check if the columns registered in self.tfs_list are the same as the ones
        in the passed df
        Returns:
            bool: Return True if the columns match, raise an exception otherwise
        """

        diff = list(set(self.tfs_list["cols"]) ^ set(df.columns))
        if len(diff) > 0:
            raise Exception("Columns in fitted and transformed DataFrame do not match: {}".format(diff))

        if list(self.tfs_list["cols"]) == list(df.columns):
            return True

        raise Exception("Columns in EncoderBlueprint and DataFrame do not have the same order")

    def _perform_na_fit(self, df, y):
        raise NotImplementedError()

    def _perform_na_transform(self, df):
        raise NotImplementedError()

    def _perform_categ_fit(self, df, y):
        raise NotImplementedError()

    def _perform_categ_transform(self, df):
        raise NotImplementedError()

    def fit(self, X, y=None, **kwargs):
        """
        Fit encoder according to X and y.
        The features from the `X` DataFrame which are not passed in `numeric_cols` or `categorical_cols`
        are just ignored during transformation.
        This method will fir the `X` dataset to achieve the following:
            - Remove NaN values by using the feature mean and adding a feature_missing feature
            - Scale the numeric values according to the EncoderBlueprint scaler
            - Encode categorical features to numeric types
        What it doesn't do:
            - Deal with outliers
        Args:
            X (pd.DataFrame): Array of DataFrame of shape = [n_samples, n_features]
                Training vectors, where n_samples is the number of samples
                and n_features is the number of features.
            y (str): Column name of the target value of X. The column must be contained in X.
        Returns:
            self : encoder
                Returns self.
        """
        all_feat = self.categorical_vars + self.numeric_vars
        df = X[[feat for feat in all_feat if feat in X.columns]].copy()
        if y is not None:
            self.tfs_list["y"] = X[y]

        # Missing values
        # TODO for ordered data (e.g. time series), take the adjacent value — next or previous
        if self.fix_missing:
            self._perform_na_fit(df, y)
            self._perform_na_transform(df)

        # Categorical columns
        # http://contrib.scikit-learn.org/categorical-encoding/
        self._perform_categ_fit(df, y)
        self._perform_categ_transform(df)

        # Scaling
        num_cols = [n for n in df.columns if is_numeric_dtype(df[n]) and n in self.numeric_vars]
        self.tfs_list["num_cols"] = num_cols
        if self.numeric_scaler is not None:
            # Turning all the columns to the same dtype before scaling is important
            self.numeric_scaler.fit(df[num_cols].astype(np.float32).values)

        self.tfs_list["cols"] = df.columns
        del df
        return self

    def transform(self, X):
        """
        Perform the transformation to new data.
        X (pd.DataFrame): Array of DataFrame of shape = [n_samples, n_features]
                Training vectors, where n_samples is the number of samples
                and n_features is the number of features.

        Returns:

        """
        all_feat = self.categorical_vars + self.numeric_vars
        missing_col = [col for col in X.columns if col not in all_feat]
        df = X[[feat for feat in all_feat if feat in X.columns]].copy()

        if self.fix_missing:
            print("Warning: Missing columns: {}, dropping them...".format(missing_col))
            print("--- Fixing NA values ({}) ---".format(len(self.tfs_list["missing"])))
            self._perform_na_transform(df)
            print("List of NA columns fixed: {}".format(list(self.tfs_list["missing"])))
            print("Categorizing features {}".format(self.categorical_vars))

        # Categorical columns
        self._perform_categ_transform(df)

        # Scaling
        if self.numeric_scaler is not None:
            num_cols = self.tfs_list["num_cols"]
            # Turning all the columns to the same dtype before scaling is important
            df[num_cols] = self.numeric_scaler.transform(df[num_cols].astype(np.float32).values)
            print("List of scaled columns: {}".format(num_cols))

        # Print stats
        non_num_cols = self._get_all_non_numeric(df)
        nan_ratio = df.isnull().sum() / len(df)

        print("------- Dataframe of len {} summary -------\n".format(len(df.columns)))
        for col, nan, dtype in zip(df.columns, nan_ratio.values, df.dtypes.values):
            print("Column {:<30}:\t dtype: {:<10}\t NaN ratio: {}".format(col, str(dtype), nan))
        if len(non_num_cols) > 0:
            raise Exception("Not all columns are numeric: {}.".format(non_num_cols))
        if self.fix_missing and nan_ratio.all() > 0:
            raise Exception("NaN has been found!")

        self._check_integrity(df)
        print("---------- Preprocessing done -----------")
        return df


class TreeEncoder(BaseEncoder):
    def __init__(self, numeric_vars, categorical_vars, fix_missing=True, numeric_scaler=None):
        """
            An encoder to encode data from structured (tabular) data
            used for tree based models (RandomForests, GBTs) as well
            as deep neural networks with categorical embeddings features (DNN)
        Args:
            numeric_vars (list): The list of variables to encode as numeric values.
            categorical_vars (list): The list of variables to encode as categorical.
            fix_missing (bool): True to fix the missing values (will add a new feature `is_missing` and replace
                the missing value by its median). For some models like Xgboost you may want to set this value to False.
            numeric_scaler (None, Scaler): None or a scaler from sklearn.preprocessing.data for scaling numeric features
                All features types will be encoded as float32.
                An sklearn StandardScaler() will fit most common cases.
                For a more robust scaling with outliers take a look at RankGauss:
                    https://www.kaggle.com/c/porto-seguro-safe-driver-prediction/discussion/44629
                and rankdata:
                    https://docs.scipy.org/doc/scipy-0.16.0/reference/generated/scipy.stats.rankdata.html

            Reference -> http://scikit-learn.org/stable/auto_examples/preprocessing/plot_all_scaling.html
        """
        super().__init__(numeric_vars, categorical_vars, fix_missing, numeric_scaler)

    def _perform_na_fit(self, df, y):
        missing = {}
        all_feat = self.categorical_vars + self.numeric_vars
        for feat in all_feat:
            if is_numeric_dtype(df[feat]):
                if pd.isnull(df[feat]).sum():
                    median = df[feat].median()
                    missing[feat] = median
        self.tfs_list["missing"] = missing

    def _perform_na_transform(self, df):
        for col, median in self.tfs_list["missing"].items():
            df[col + '_na'] = df[col].isnull()
            df[col].fillna(median, inplace=True)

    def _perform_categ_fit(self, df, y):
        categ_cols = {}
        for col in self.categorical_vars:
            if col in df.columns:
                categs = pd.factorize(df[col], na_sentinel=0, order=True)[1]
                categ_cols[col] = categs
        self.tfs_list["categ_cols"] = categ_cols

    def _perform_categ_transform(self, df):
        for col, vals in self.tfs_list["categ_cols"].items():
            # "n/a" category will be encoded as 0
            df[col] = df[col].astype(pd.api.types.CategoricalDtype(categories=vals, ordered=True)).cat.codes + 1


class LinearEncoder(BaseEncoder):
    def __init__(self, numeric_vars, categorical_vars, fix_missing, numeric_scaler=None, categ_enc_method=None):
        """
            An encoder used for linear based models (Linear/Logistic regression) as well
            as deep neural networks without embeddings.
        Args:
            numeric_vars (list): The list of variables to encode as numeric values.
            categorical_vars (list): The list of variables to encode as categorical.
            fix_missing (bool): True to fix the missing values (will add a new feature `is_missing` and replace
                the missing value by its median). For some models like Xgboost you may want to set this value to False.
            numeric_scaler (None, Scaler): None or a scaler from sklearn.preprocessing.data for scaling numeric features
                All features types will be encoded as float32.
                An sklearn StandardScaler() will fit most common cases.
                For a more robust scaling with outliers take a look at RankGauss:
                    https://www.kaggle.com/c/porto-seguro-safe-driver-prediction/discussion/44629
                and rankdata:
                    https://docs.scipy.org/doc/scipy-0.16.0/reference/generated/scipy.stats.rankdata.html

            Reference -> http://scikit-learn.org/stable/auto_examples/preprocessing/plot_all_scaling.html
            categ_enc_method (str): If a given categorical column cardinality is < 10 then one hot encoding
            will be used. For cardinality >= 10 one of the following methods can be used:
                - "hashing": Better known as the "hashing trick"
                - "target": Also known as Mean encoding/Target encoding/Likelihood encoding.
                    The implementation is based on the Expanding mean scheme
                - "force-onehot": Force onehot encoding for large cardinality features.
                    Consider using one_hot_encode_sparse() instead to get a sparse matrix with lower
                    memory footprint.
        """
        super().__init__(numeric_vars, categorical_vars, fix_missing, numeric_scaler)
        self.categ_enc_method = categ_enc_method.lower()
        self.hash_space = 25

    def _perform_na_fit(self, df, y):
        missing = []
        all_feat = self.categorical_vars + self.numeric_vars
        for feat in all_feat:
            if is_numeric_dtype(df[feat]):
                if pd.isnull(df[feat]).sum():
                    missing.append(feat)
        self.tfs_list["missing"] = missing

    def _perform_na_transform(self, df):
        for col in self.tfs_list["missing"]:
            df[col].fillna(-999999, inplace=True)

    def _perform_categ_fit(self, df, y):
        # https://github.com/scikit-learn-contrib/categorical-encoding
        # https://tech.yandex.com/catboost/doc/dg/concepts/algorithm-main-stages_cat-to-numberic-docpage/
        # https://en.wikipedia.org/wiki/Feature_hashing#Feature_vectorization_using_the_hashing_trick
        categ_cols = {}
        for col in self.categorical_vars:
            categs = df[col].astype(pd.api.types.CategoricalDtype()).cat.categories
            if df[col].nunique() < 10 or self.categ_enc_method == "force-onehot":
                lenc = LabelEncoder()
                df[col] = lenc.fit_transform(df[col].values) + 1
                # Create an internal sparse matrix
                enc = OneHotEncoder(n_values=len(lenc.classes_) + 1)  # +1 to handle missing values
                enc.fit(df[[col]].values)
                if len(lenc.classes_) > 10:
                    print("Warning, cardinality of {} = {}".format(col, len(lenc.classes_)))
                categ_cols[col] = {"onehot": (enc, lenc.classes_)}
            else:
                if self.categ_enc_method == "target":
                    if self.tfs_list["y"] is None:
                        raise Exception("You have to pass your target variable to the fit() "
                                        "function for target encoding")
                    # Otherwise use Mean/target/likelihood encoding
                    df[self.tfs_list["y"].name] = self.tfs_list["y"]
                    cumsum = df.groupby(col)[self.tfs_list["y"].name].cumsum() - df[self.tfs_list["y"].name]
                    cumcnt = df.groupby(col)[self.tfs_list["y"].name].cumcount()
                    means = cumsum / cumcnt
                    means.rename('mean_enc', inplace=True)
                    concat = pd.concat([means, self.tfs_list["y"]], axis=1)
                    categ_cols[col] = {"target": concat}
                    raise NotImplementedError("This encoding is not yet implemented")
                elif self.categ_enc_method == "hashing":
                    str_hashs = [col + "=" + str(val) for val in categs]
                    hashs = [hash(h) % self.hash_space for h in str_hashs]
                    categ_cols[col] = {"hashing": hashs}
                else:
                    categ_cols[col] = {"none": None}

        self.tfs_list["categ_cols"] = categ_cols

    def _perform_categ_transform(self, df):
        for col, item in self.tfs_list["categ_cols"].items():
            method = next(iter(item.keys()))
            if method == "none":
                print("Warning, no encoding set for feature {}".format(col))
            elif method == "onehot":
                enc = list(item.values())[0][0]
                classes = list(item.values())[0][1]
                # onehot[:, 1:]] to avoid collinearity
                onehot = enc.transform(df[[col]].values)[:, 1:].toarray()
                columns = [col + "_unknown"] + [col + "_" + str(c) for c in classes[1:]]
                res = pd.DataFrame(data=onehot, columns=columns)
                df = pd.concat([df.drop(col, axis=1), res], axis=1)
            elif method == "target":
                # TODO BE CAREFUL of the following points:
                # • Local experiments:
                #   ‒ Estimate encodings on X_train
                #   ‒ Map them to X_train and X_val
                #   ‒ Regularize on X_train
                #   ‒ Validate the model on X_train / X_val split
                # • Submission:
                #   ‒ Estimate encodings on whole Train data
                #   ‒ Map them to Train and Test
                #   ‒ Regularize on Train
                #   ‒ Fit on Train
                enc = list(item.values())[0]
                df[col + "_mean_target"] = df[col].map(enc)
            elif method == "hashing":
                categs = df[col].astype(pd.api.types.CategoricalDtype()).cat.codes
                str_hashs = [col + "=" + str(val) for val in categs]
                hashs = [hash(h) % self.hash_space for h in str_hashs]
                df[col] = hashs


def one_hot_encode_sparse(df, target_cols):
    """
    One-hot encode the given columns and return a sparse
    matrix
    Returns:
        DataFrame: The original DataFrame + Onehot encoded values
    """