from asyncpg import Pool, Record

from typing import Self, Any, Literal
from abc import ABC, abstractmethod

class Condition:
    def __init__(self, 
        field: str, *,
        value: Any,
        inject: bool = False,
        in_list: bool = False,
        sign: str = "="
    ) -> None:
        self.field = field          # table field 
        self.sign = sign            # <= >= < > = 
        self.value = value          # value to match with
        self.inject = inject        # whether to directly inject to statement (avoid)
                                    # note that value needs to be exact string representation if true
        self.in_list = in_list      # whether searching IN list

    def parse(self, arg_num: int) -> str:
        """
        Returns parsed argument, where `arg_num` is argument number

        if self.inject is true, `arg_num` will not be used
        """
        # if self.inject is false, parse as parameter
        raw_arg = self.value if self.inject else f"${arg_num}"
        
        # if searching IN list, use ANY(raw_arg)
        # e.g. my_col = ANY($1), same as my_col IN $1 
        # ... but latter doesnt work parameterised
        arg = f"ANY({raw_arg})" if self.in_list else raw_arg
        
        return f"{self.field} {self.sign} {arg}"

    def __str__(self) -> str:
        # just returns field name and sign
        return f"{self.field} {self.sign}"
        
class Conditions:
    def __init__(self, delimiter: str = "AND", *conditions: Condition) -> None:
        
        # this variable denotes how to separate conditions (e.g. with AND or OR)
        self.delimiter = delimiter

        # if list is empty, or None passed in
        # just create an object with basically no where conditions
        self._conds: list[Condition] = []
        self._values = []

        for cond in conditions:
            if cond is None:
                break
            
            # append to list of Condition
            self._conds.append(cond)

            # value will not be injected
            if not cond.inject:
                self._values.append(cond.value)

    def parse(self, start: int = 1) -> str:
        """
        Gets conditions parsed for WHERE clause

        Note that it does not add the "WHERE" before the conditions.
        Use a WhereContainer for complete parsing 
        """
        # return an empty WHERE clause if conditions list is empty
        if not self._conds:
            return ""
        
        arg_num = start     # arg number
        args = []           # str list of parsed args

        for cond in self._conds:
            args.append(cond.parse(arg_num))
            # arg_num only increments if value not injected
            arg_num += 1 if not cond.inject else 0
        
        return f" {self.delimiter} ".join(args)
    
    @property
    def conditions(self) -> list[Condition]:
        return self._conds

    @property
    def values(self) -> list[Any]:
        """
        Get list of values in same order as where clause

        Removes all values that will be injected
        """
        return self._values
    
    def __len__(self) -> int:
        """
        Returns length of values 
        i.e. number of parameters reserved for WHERE conditions
        """
        return len(self._values)

class OrderBy:
    def __init__(self, order_by_col: str, order_by_type: Literal["ASC", "DESC"] = "DESC") -> None:
        self.column = order_by_col
        self.type_ = order_by_type

    def __str__(self) -> str:
        return f"{self.column} {self.type_}"

class OrderBys:
    def __init__(self, *order_bys: OrderBy) -> None:
        # if list is empty, or None passed in
        # just create an object with no order by condition
        if (not order_bys) or None in order_bys:
            self._order_bys = []
        else:
            self._order_bys = list(order_bys)

    def add(self, *order_bys: OrderBy):
        self._order_bys += list(order_bys)

    def parse(self) -> str:
        """
        Get a complete parsed ORDER BY clause
        """
        # return an empty ORDER BY clause if _order_bys is empty
        if not self._order_bys:
            return ""
        
        return "ORDER BY " + ", ".join(str(order_by) for order_by in self._order_bys)
    
    @property
    def order_bys(self) -> list[OrderBy]:
        return self._order_bys

class Update:
    def __init__(self, column: str, value: Any, as_change: bool = False) -> None:
        self.column = column
        self.value = value
        self._as_change = as_change

    def __str__(self) -> str:
        if self._as_change:
            return f"{self.column} = {self.column} +"
        else:
            return f"{self.column} ="

class WhereContainer:
    def __init__(self, *conditions: Conditions) -> None:
        self._conditions = list(conditions)

    def add(self, delimiter: str = "AND", *conditions: Condition):
        self._conditions.append(Conditions(delimiter, *conditions))

    @property
    def conditions(self) -> list[Condition]:
        individual_conds = []

        for conds in self._conditions:
            individual_conds += conds.conditions

        return individual_conds

    @property
    def values(self) -> list[Any]:
        """
        Get list of values in same order as where clause

        Removes all values that will be injected
        """
        vals = []

        for conds in self._conditions:
            # getting values of all Conditions object
            vals += conds.values

        return vals
    
    def __len__(self) -> int:
        """
        Returns length of values 
        i.e. number of parameters reserved for WHERE conditions
        """
        length = 0

        for conds in self._conditions:
            length += len(conds)

        return length
    
    def parse(self, start: int = 1):
        
        first_conds = True
        parsed = ""
        arg_num = start

        # iterates through Conditions objects
        for conditions in self._conditions:
            # if this is the first Conditions object
            if first_conds:
                # if it is empty continue to next one
                if not conditions.conditions:
                    continue
                
                # eg: "WHERE arg = $1"
                parsed = "WHERE " + conditions.parse(arg_num)
                
                # now that we have used the first Conditions object, set it to False
                first_conds = False

            else:
                # eg: " AND arg2 = $2"
                parsed += f" {conditions.delimiter} " + conditions.parse(arg_num)

            # start next arg nums after ones reserved here
            arg_num += len(conditions)
            
        return parsed


class Query(ABC):
    def __init__(
        self, *,
        table_name: str
    ) -> None:
        self.table_name = table_name
        # no where clause, but can be added with where()
        self.where_container = WhereContainer()

        # no order by clause, but can be added with order_by() 
        self.order_by_container = OrderBys()

    def where(self, delimiter: Literal["AND", "OR"], *conditions: Condition) -> Self:
        # making sure atleast 1 Condition object passed in
        if not conditions:
            raise ValueError("Expected atleast 1 Condition argument, recieved none")
        
        self.where_container.add(delimiter, *conditions)
        return self

    def order_by(self, *order: OrderBy) -> Self:
        self.order_by_container.add(*order)
        return self

    @property
    def values(self):
        """
        Returns values for WHERE $ args
        """
        return self.where_container.values

    @abstractmethod
    def __str__(self):
        ...

class Select(Query):
    def __init__(self, table_name: str, *columns: str) -> None:
        super().__init__(table_name = table_name)
        self.columns = list(columns)
        self._limit = None
        self._exists = False

    def limit(self, limit_to: int) -> Self:
        self._limit = limit_to

        return self

    def exists(self) -> Self:
        self._exists = True

        return self
    
    def __str__(self):
        # if list is empty, fetch all columns
        parsed_columns = ", ".join(self.columns) if self.columns else "*"

        # limit should only be there if limit is not None
        parsed_limit = f"LIMIT {self._limit}" if self._limit is not None else ""

        parsed_where = self.where_container.parse()
        parsed_order = self.order_by_container.parse()

        parsed_query = f"""
        SELECT {parsed_columns} FROM {self.table_name}
        {parsed_where}
        {parsed_order}
        {parsed_limit};
        """

        if self._exists:
            # wrap up parsed SELECT query in SELECT EXISTS()
            return f"SELECT EXISTS ({parsed_query})"
        
        # otherwise just return SELECT query parsed
        return parsed_query
    

    async def fetch(self, pool: Pool) -> list:
        return await pool.fetch(str(self), *self.values)
    
    async def fetchrow(self, pool: Pool) -> Record | None:
        return await pool.fetchrow(str(self), *self.values)
    
    async def fetchval(self, pool: Pool) -> Any | None:
        return await pool.fetchval(str(self), *self.values)

class UpdateQ(Query):
    def __init__(self, table_name: str, *updates: Update) -> None:
        super().__init__(table_name = table_name)
        self.updates = list(updates)
        self._update_values = [update.value for update in self.updates]

    def __len__(self) -> int:
        """
        Returns length of update values for update $ args only
        """
        return len(self._update_values)

    def __str__(self) -> str:
        # parse "col1 = $1, col2 = $2, ..." from enumerated Update objects
        args = ", ".join(f"{update} ${i}" for i, update in enumerate(self.updates, start = 1))
        
        # making sure WHERE clause arg numbers start after UPDATE arg numbers
        where_clause = self.where_container.parse(len(self) + 1)

        # update statement
        return f"""
            UPDATE {self.table_name} 
            SET {args}
            {where_clause};
            """

    @property
    def values(self):
        """
        Returns values for update and where $ args, in order
        """
        return self._update_values + self.where_container.values
    
    async def execute(self, pool: Pool) -> None:
        await pool.execute(str(self), *self.values)

class Insert(Query):
    def __init__(self, table_name: str, **insert_params) -> None:
        super().__init__(table_name = table_name)
        self._fields = insert_params.keys()
        self._values = insert_params.values()

    @property
    def values(self) -> list[Any]:
        """
        Returns insert param values
        """
        return list(self._values)

    def __str__(self):
        
        fields = ", ".join(self._fields)
        # parse arg nums so it is 1 to number of insert fields (inclusive)
        arg_nums = ", ".join(f"${i}" for i in range(1, len(self._fields) + 1))

        return f"""
        INSERT INTO {self.table_name} ({fields})
        VALUES ({arg_nums});
        """
    
    async def execute(self, pool: Pool):
        await pool.execute(str(self), *self.values)

class Delete(Query):
    def __str__(self):
        parsed_where = self.where_container.parse()

        return f"""
            DELETE FROM {self.table_name}
            {parsed_where};
            """

    async def execute(self, pool: Pool):
        await pool.execute(str(self), *self.values)

class MyORM:
    def __init__(
            self, 
            table_name: str
    ) -> None:
        self.table_name = table_name

    def select(self, *fields: str) -> Select:
        """
        Enter no fields if you want to fetch all fields
        """
        return Select(self.table_name, *fields)
    
    
    def update(self, *updates: Update) -> UpdateQ:
        return UpdateQ(self.table_name, *updates)
        
    def insert(self, **insert_params) -> Insert:
        return Insert(self.table_name, **insert_params)        

    def delete(self) -> Delete:
        return Delete(table_name = self.table_name)
