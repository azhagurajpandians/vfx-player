# Early runtime hook to suppress warnings before setuptools/pkg_resources imports
import warnings
warnings.filterwarnings("ignore")
